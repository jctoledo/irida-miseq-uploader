import sys
import json
import webbrowser
import re
from os import path, getcwd, pardir, listdir, walk
from os import system, getcwd, chdir, makedirs, sep
from fnmatch import filter as fnfilter
from threading import Thread
from time import time
from math import ceil
from copy import deepcopy
from Queue import Queue
from ConfigParser import RawConfigParser

from shutil import copy2

import wx
from wx.lib.agw.genericmessagedialog import GenericMessageDialog as GMD
from wx.lib.agw.multidirdialog import MultiDirDialog as MDD
from wx.lib.newevent import NewEvent
from pubsub import pub
from appdirs import user_config_dir

from Parsers.miseqParser import (
    complete_parse_samples, parse_metadata)
from Model.SequencingRun import SequencingRun
from Validation.onlineValidation import (
    project_exists, sample_exists)
from Validation.offlineValidation import (validate_sample_sheet,
                                          validate_pair_files,
                                          validate_sample_list)
from Exceptions.ProjectError import ProjectError
from Exceptions.SampleError import SampleError
from Exceptions.SampleSheetError import SampleSheetError
from Exceptions.SequenceFileError import SequenceFileError
from GUI.SettingsFrame import SettingsFrame, ConnectionError

path_to_module = path.dirname(__file__)
user_config_dir = user_config_dir("iridaUploader")
user_config_file = path.join(user_config_dir, "config.conf")

if len(path_to_module) == 0:
    path_to_module = '.'


class MainPanel(wx.Panel):

    def __init__(self, parent):

        self.parent = parent
        self.WINDOW_SIZE = self.parent.WINDOW_SIZE
        wx.Panel.__init__(self, parent)

        self.send_seq_files_evt, self.EVT_SEND_SEQ_FILES = NewEvent()

        self.conf_parser = RawConfigParser()
        self.config_file = user_config_file
        check_config_dirs(self.conf_parser)
        self.conf_parser.read(self.config_file)

        self.sample_sheet_files = []
        self.seq_run_list = []
        self.browse_path = self.get_config_default_dir()

        self.dir_dlg = None
        self.api = None
        self.upload_complete = None
        self.curr_upload_id = None
        self.loaded_upload_id = None
        self.uploaded_samples_q = None
        self.prev_uploaded_samples = []
        self.mui_created_in_handle_api_thread_error = False

        self.LABEL_TEXT_WIDTH = 80
        self.LABEL_TEXT_HEIGHT = 32
        self.CF_LABEL_TEXT_HEIGHT = 52
        self.VALID_SAMPLESHEET_BG_COLOR = wx.GREEN
        self.INVALID_SAMPLESHEET_BG_COLOR = wx.RED
        self.LOG_PNL_REG_TXT_COLOR = wx.BLACK
        self.LOG_PNL_ERR_TXT_COLOR = wx.RED
        self.LOG_PNL_OK_TXT_COLOR = (0, 102, 0)  # dark green
        self.PADDING_LEN = 20
        self.SECTION_SPACE = 20
        self.TEXTBOX_FONT = wx.Font(
            pointSize=10, family=wx.FONTFAMILY_DEFAULT,
            style=wx.FONTSTYLE_NORMAL, weight=wx.FONTWEIGHT_NORMAL)
        self.LABEL_TXT_FONT = self.TEXTBOX_FONT

        self.padding = wx.BoxSizer(wx.VERTICAL)
        self.top_sizer = wx.BoxSizer(wx.VERTICAL)
        self.directory_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.log_panel_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ov_label_container = wx.BoxSizer(wx.HORIZONTAL)
        self.upload_speed_container = wx.BoxSizer(wx.HORIZONTAL)
        self.estimated_time_container = wx.BoxSizer(wx.HORIZONTAL)
        self.ov_upload_est_time_container = wx.BoxSizer(wx.VERTICAL)
        self.progress_bar_sizer = wx.BoxSizer(wx.VERTICAL)
        self.upload_button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_select_sample_sheet_section()
        self.add_log_panel_section()
        self.add_curr_file_progress_bar()
        self.add_overall_progress_bar()
        self.add_upload_button()

        self.top_sizer.Add(
            self.directory_sizer, proportion=0, flag=wx.ALIGN_CENTER |
            wx.EXPAND)

        self.top_sizer.AddSpacer(self.SECTION_SPACE)
        # between directory box & credentials

        self.top_sizer.Add(
            self.log_panel_sizer, proportion=1, flag=wx.EXPAND |
            wx.ALIGN_CENTER)

        self.top_sizer.Add(
            self.progress_bar_sizer,
            flag=wx.TOP | wx.BOTTOM | wx.ALIGN_CENTER | wx.EXPAND, border=5)

        self.padding.Add(
            self.top_sizer, proportion=1, flag=wx.ALL | wx.EXPAND,
            border=self.PADDING_LEN)

        self.padding.Add(
            self.upload_button_sizer, proportion=0,
            flag=wx.BOTTOM | wx.ALIGN_CENTER, border=self.PADDING_LEN)

        self.SetSizer(self.padding)
        self.Layout()

        # Updates boths progress bars and progress labels
        pub.subscribe(self.update_progress_bars, "update_progress_bars")

        # publisher sends a message that uploading sequence files is complete
        # basically places a call to self.update_progress_bars in the event q
        pub.subscribe(self.pair_seq_files_upload_complete,
                      "pair_seq_files_upload_complete")

        # Called by an api function
        # display error message and update sequencing run uploadStatus to ERROR
        pub.subscribe(self.handle_api_thread_error,
                      "handle_api_thread_error")

        # update self.api when Settings is closed
        # if it's not None (i.e can connect to API) enable the submit button
        pub.subscribe(self.set_updated_api,
                      "set_updated_api")

        # Updates upload speed and estimated remaining time labels
        pub.subscribe(self.update_remaining_time, "update_remaining_time")

        # displays the completion command message in to the log panel
        pub.subscribe(self.display_completion_cmd_msg,
                      "display_completion_cmd_msg")

        self.Bind(self.EVT_SEND_SEQ_FILES, self.handle_send_seq_evt)
        self.settings_frame = SettingsFrame(self)
        self.settings_frame.Hide()
        self.Center()
        self.Show()
	# auto-scan the currently selected directory (which should be the directory
	# that's set in the preferences file).
        self.browse_path = self.dir_box.GetValue()
        self.start_sample_sheet_processing(first_start = True)

    def get_config_default_dir(self):

        """
        Check if the config has a default_dir.  If not set to
        the user's home directory.

        return the path to the default directory from the config file
        """

        default_dir_path = self.conf_parser.get("Settings", "default_dir")

        # if the path is not set, set to home directory
        if not default_dir_path:

            # set default directory to be the user's home directory
            default_dir_path = path.expanduser("~")

        return default_dir_path

    def handle_send_seq_evt(self, evt):

        """
        function bound to custom event self.EVT_SEND_SEQ_FILES
        creates new thread for sending pair sequence files

        no return value
        """

        kwargs = {
            "samples_list": evt.sample_list,
            "callback": evt.send_pairs_callback,
            "upload_id": evt.curr_upload_id,
            "prev_uploaded_samples": evt.prev_uploaded_samples,
            "uploaded_samples_q": evt.uploaded_samples_q
        }
        self.api.send_pair_sequence_files(**kwargs)

    def add_select_sample_sheet_section(self):

        """
        Adds data directory text label, text box and button in to panel
        Sets a tooltip when hovering over text label, text box or button
            describing what file needs to be selected

        Clicking the browse button or the text box launches the file dialog so
            that user can select SampleSheet file

        no return value
        """

        self.browse_button = wx.Button(self, label="Choose directory")
        self.browse_button.SetFocus()
        self.dir_label = wx.StaticText(parent=self, id=-1, label="File path")
        self.dir_label.SetFont(self.LABEL_TXT_FONT)
        self.dir_box = wx.TextCtrl(
            self, size=(-1, self.browse_button.GetSize()[1]),
            style=wx.TE_PROCESS_ENTER)
        self.dir_box.SetFont(self.TEXTBOX_FONT)
        self.dir_box.SetValue(self.browse_path)

        self.directory_sizer.Add(self.dir_label, flag=wx.ALIGN_CENTER_VERTICAL)
        self.directory_sizer.Add(self.dir_box, proportion=1, flag=wx.EXPAND)
        self.directory_sizer.Add(self.browse_button)

        tip = "Select the directory containing the SampleSheet.csv file " + \
            "to be uploaded"
        self.dir_box.SetToolTipString(tip)
        self.dir_label.SetToolTipString(tip)
        self.browse_button.SetToolTipString(tip)

        self.Bind(wx.EVT_BUTTON, self.open_dir_dlg, self.browse_button)
        self.Bind(wx.EVT_TEXT_ENTER, self.manually_enter_dir, self.dir_box)

    def manually_enter_dir(self, evt):

        """
        Function bound to user typing in to the dir_box and then pressing
        the enter key.
        Sets self.browse_path to the value enterred by the user because
        self.browse_path is used in self.start_sample_sheet_processing()

        no return value
        """

        self.browse_path = self.dir_box.GetValue()
        self.start_sample_sheet_processing()

    def add_curr_file_progress_bar(self):

        """
        Adds current file progress bar. Will be used for displaying progress of
            the current sequence file pairs being uploaded.

        no return value
        """

        self.cf_init_label = "\n\nFile: 0%"
        self.cf_progress_label = wx.StaticText(
            self, id=-1,
            size=(-1, self.CF_LABEL_TEXT_HEIGHT),
            label=self.cf_init_label)
        self.cf_progress_label.SetFont(self.LABEL_TXT_FONT)
        self.cf_progress_bar = wx.Gauge(self, range=100,
                                        size=(-1, self.LABEL_TEXT_HEIGHT))
        self.progress_bar_sizer.Add(self.cf_progress_label)
        self.progress_bar_sizer.Add(self.cf_progress_bar, proportion=1,
                                    flag=wx.EXPAND)
        self.cf_progress_label.Hide()
        self.cf_progress_bar.Hide()

    def add_overall_progress_bar(self):

        """
        Adds overall progress bar. Will be used for displaying progress of
            all sequence files uploaded.

        no return value
        """

        self.ov_init_label = "\nOverall: 0%"
        self.ov_upload_init_static_label = "Upload speed: "
        self.ov_est_time_init_static_label = "Estimated time remaining: "
        self.ov_upload_init_label = "..."
        self.ov_est_time_init_label = "..."

        self.ov_progress_label = wx.StaticText(
            self, id=-1,
            label=self.ov_init_label)

        self.ov_upload_static_label = wx.StaticText(
            self, id=-1,
            label=self.ov_upload_init_static_label)
        self.ov_upload_label = wx.StaticText(
            self, id=-1,
            label=self.ov_upload_init_label)

        self.ov_est_time_static_label = wx.StaticText(
            self, id=-1,
            label=self.ov_est_time_init_static_label)
        self.ov_est_time_label = wx.StaticText(
            self, id=-1,
            label=self.ov_est_time_init_label)

        self.ov_progress_label.SetFont(self.LABEL_TXT_FONT)
        self.ov_upload_static_label.SetFont(self.LABEL_TXT_FONT)
        self.ov_upload_label.SetFont(self.LABEL_TXT_FONT)
        self.ov_est_time_static_label.SetFont(self.LABEL_TXT_FONT)
        self.ov_est_time_label.SetFont(self.LABEL_TXT_FONT)

        self.ov_progress_bar = wx.Gauge(self, range=100,
                                        size=(-1, self.LABEL_TEXT_HEIGHT))

        self.ov_label_container.Add(self.ov_progress_label)
        self.ov_label_container.AddStretchSpacer()

        self.upload_speed_container.Add(self.ov_upload_static_label)
        self.upload_speed_container.Add(self.ov_upload_label)

        self.estimated_time_container.Add(self.ov_est_time_static_label)
        self.estimated_time_container.Add(self.ov_est_time_label)

        self.ov_upload_est_time_container.Add(self.upload_speed_container)
        self.ov_upload_est_time_container.Add(self.estimated_time_container)
        self.ov_label_container.Add(self.ov_upload_est_time_container,
                                    flag=wx.ALIGN_RIGHT)
        self.progress_bar_sizer.AddSpacer(self.SECTION_SPACE)
        self.progress_bar_sizer.Add(self.ov_label_container, flag=wx.EXPAND)
        self.progress_bar_sizer.Add(self.ov_progress_bar, proportion=1,
                                    flag=wx.EXPAND)

        self.ov_progress_label.Hide()
        self.ov_upload_static_label.Hide()
        self.ov_upload_label.Hide()
        self.ov_est_time_static_label.Hide()
        self.ov_est_time_label.Hide()
        self.ov_progress_bar.Hide()

    def add_upload_button(self):

        """
        Adds upload button to panel

        no return value
        """

        self.upload_button = wx.Button(self, label="Upload")
        self.upload_button.Disable()

        self.upload_button_sizer.Add(self.upload_button)
        self.Bind(wx.EVT_BUTTON, self.upload_to_server, self.upload_button)

        tip = "Upload sequence files to IRIDA server. " + \
            "Select a valid SampleSheet file to enable button."
        self.upload_button.SetToolTipString(tip)

    def add_log_panel_section(self):

        """
        Adds log panel text control for displaying progress and errors

        no return value
        """

        self.log_panel = wx.TextCtrl(
            self, id=-1,
            value="",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)

        value = ("Waiting for user to select directory containing " +
                 "SampleSheet file.\n\n")

        self.log_panel.SetFont(self.TEXTBOX_FONT)
        self.log_panel.SetForegroundColour(self.LOG_PNL_REG_TXT_COLOR)
        self.log_panel.AppendText(value)
        self.log_panel_sizer.Add(self.log_panel, proportion=1, flag=wx.EXPAND)

    def display_warning(self, warn_msg, dlg_msg=""):

        """
        Displays warning message as a popup and writes it in to log_panel

        arguments:
                warn_msg -- message to display in warning dialog message box
                dlg_msg -- optional message to display in warning dialog
                           message box. If this is not an empty string
                           then the string message here will be displayed for
                           the pop up dialog instead of warn_msg.

        no return value
        """

        self.log_color_print(warn_msg + "\n", self.LOG_PNL_ERR_TXT_COLOR)

        if len(dlg_msg) > 0:
            msg = dlg_msg
        else:
            msg = warn_msg

        self.warn_dlg = GMD(
            parent=self, message=msg, caption="Warning!",
            agwStyle=wx.OK | wx.ICON_EXCLAMATION)

        self.warn_dlg.Message = warn_msg  # for testing
        if self.warn_dlg:
            self.warn_dlg.Destroy()

    def log_color_print(self, msg, color=None):

        """
        print colored text to the log_panel
        if no color provided then just uses self.LOG_PNL_REG_TXT_COLOR
        as default

        arguments:
            msg -- the message to print
            color -- the color to print the message in

        no return value
        """

        if color is None:
            color = self.LOG_PNL_REG_TXT_COLOR

        text_attrib = wx.TextAttr(color)

        start_color = len(self.log_panel.GetValue())
        end_color = start_color + len(msg)

        self.log_panel.AppendText(msg)
        self.log_panel.SetStyle(start_color, end_color, text_attrib)
        self.log_panel.AppendText("\n")

    def close_handler(self, event):

        """
        Function bound to window/MainFrame being closed (close button/alt+f4)

        if self.upload_complete is False that means the program was closed
        while an upload was still running.
        Set that SequencingRun's uploadStatus to ERROR.

        in the event that the program is closed during mid-upload -
        if .miseqUploaderInfo was not already created in
        handle_api_thread_error() then try create it here
        write all uploaded sample id in to .miseqUploaderInfo
        if uploaded_samples_q is empty that should mean that the
        upload is complete and handle_upload_complete() already created
        the .miseqUploaderInfo or there were no uploads in this session

        Destroy SettingsFrame and then destroy self

        no return value
        """

        self.log_color_print("Closing")
        if all([self.upload_complete is not None,
                self.curr_upload_id is not None,
                self.upload_complete is False]):
            self.log_color_print("Updating sequencing run upload status. " +
                                 "Please wait.", self.LOG_PNL_ERR_TXT_COLOR)
            wx.Yield()
            t = Thread(target=self.api.set_pair_seq_run_error,
                       args=(self.curr_upload_id,))
            t.start()

            if not self.mui_created_in_handle_api_thread_error:
                uploaded_samples = []
                while not self.uploaded_samples_q.empty():
                    uploaded_samples.append(self.uploaded_samples_q.get())

                self.create_miseq_uploader_info_file(uploaded_samples)

        self.settings_frame.Destroy()
        self.Destroy()
        sys.exit(0)

    def start_cf_progress_bar_pulse(self):

        """
        pulse self.cf_progress_bar (move bar left and right) until uploading
        sequence file starts
        small indication that program is processing and is not frozen
        the pulse stops when self.pulse_timer.Stop() is called in
        self.update_progress_bars()

        no return value
        """

        pulse_interval = 100  # milliseconds
        self.pulse_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda evt: self.cf_progress_bar.Pulse(),
                  self.pulse_timer)
        self.pulse_timer.Start(pulse_interval)

    def do_online_validation(self):

        """
        in each run check that each sample in the sample list has a
        project_id that already exists in IRIDA
        if project_id doesn't exist in IRIDA then the SequencingRun is removed
        from the list of sequencing runs and an error message is dispalyed

        if all samples in all SequencingRuns have a project_id
        that exists in IRIDA
            return True
        else
            return False
        """

        wx.CallAfter(self.log_color_print,
                     "Performing online validation on all sequencing runs.\n")
        api = self.api

        valid = True
        try:
            for sr in self.seq_run_list[:]:

                for sample in sr.get_sample_list():

                    if project_exists(api, sample.get_project_id()) is False:
                        msg = ("The Sample_Project: {pid} doesn't exist in " +
                               "IRIDA for Sample_Id: {sid}").format(
                                sid=sample.get_id(),
                                pid=sample.get_project_id())
                        raise ProjectError(msg)

        except ProjectError, e:
            valid = False
            wx.CallAfter(self.pulse_timer.Stop)
            wx.CallAfter(self.cf_progress_bar.SetValue, 0)
            wx.CallAfter(self.display_warning, e.message)

            self.seq_run_list.remove(sr)

        return valid

    def _upload_to_server(self):

        """
        Threaded function from upload_to_server.
        Running on a different thread so that the GUI thread doesn't get
        blocked (i.e the progress bar pulsing doesn't stop/"freeze" when
        making api calls)

        perform online validation before uploading

        uploads each SequencingRun in self.seq_run_list to irida web server

        each SequencingRun will contain a list of samples and each sample
        from the list of samples will contain a pair of sequence files

        we then check if the sample's id exists for it's given project_id
        if it doesn't exist then create it

        create and execute event: self.send_seq_files_evt which calls
        api.send_pair_sequence_files() with the list of samples and
        callback function: self.pair_upload_callback()

        no return value
        """

        api = self.api
        self.curr_upload_id = None

        try:

            if api is None:
                raise ConnectionError(
                    "Unable to connect to IRIDA. " +
                    "View Options -> Settings for more info.")

            self.upload_complete = False
            # used in close_handler() to determine if program was closed
            # while an upload is still happening in which case set
            # the sequencing run uploadStatus to ERROR
            # set to true in handle_upload_complete()

            valid = self.do_online_validation()

            if valid:

                for sr in self.seq_run_list[:]:

                    # if resuming from an upload, self.loaded_upload_id
                    # will contain the previous upload_id created
                    # else it's a new upload so create a new seq run
                    if self.loaded_upload_id is not None:
                        self.curr_upload_id = self.loaded_upload_id
                        api.set_pair_seq_run_uploading(self.curr_upload_id)
                    else:
                        json_res = api.create_paired_seq_run(
                            sr.get_all_metadata())
                        self.curr_upload_id = (
                            json_res["resource"]["identifier"])

                    # used to identify SampleSheet.csv file path
                    # when creating a .miseqUploaderInfo in
                    # create_miseq_uploader_info_file()
                    self.curr_seq_run = sr

                    for sample in sr.get_sample_list():

                        if sample_exists(api, sample) is False:
                            api.send_samples([sample])

                    wx.CallAfter(self.log_color_print,
                                 "Uploading sequencing files from: " +
                                 sr.sample_sheet_dir)

                    # if resuming upload, print to log panel
                    # and add all prev_uploaded_samples in to
                    # uploaded_samples_q so that in case the
                    # upload gets interrupted again the contents
                    # of uploaded_samples_q will be written in to
                    # .miseqUploaderInfo to enable resuming again
                    self.uploaded_samples_q = Queue()
                    if len(self.prev_uploaded_samples) > 0:
                        wx.CallAfter(self.log_color_print, "Resuming")
                        for file in self.prev_uploaded_samples:
                            self.uploaded_samples_q.put(file)

                    evt = self.send_seq_files_evt(
                        sample_list=sr.get_sample_list(),
                        send_pairs_callback=self.pair_upload_callback,
                        curr_upload_id=self.curr_upload_id,
                        prev_uploaded_samples=self.prev_uploaded_samples,
                        uploaded_samples_q=self.uploaded_samples_q)
                    self.GetEventHandler().ProcessEvent(evt)

                    self.seq_run_list.remove(sr)

        except Exception, e:
            # this catches all non-api errors
            # it won't catch api errors because they are on a diffrent thread
            # handle_api_thread_error takes care of that
            if self.curr_upload_id is not None:
                self.api.set_pair_seq_run_error(self.curr_upload_id)
                self.upload_complete = True
                self.curr_upload_id = None

            wx.CallAfter(self.pulse_timer.Stop)
            wx.CallAfter(self.cf_progress_bar.SetValue, 0)
            wx.CallAfter(
                self.display_warning, "{error_name}: {error_msg}".format(
                    error_name=e.__class__.__name__, error_msg=e.strerror))

    def upload_to_server(self, event):

        """
        Function bound to upload_button being clicked

        pulse the current file progress bar to indicate that processing
        is happening

        make threaded call to self._upload_to_server() which does the
        online validation and upload

        arguments:
                event -- EVT_BUTTON when upload button is clicked

        no return value
        """

        self.upload_button.Disable()
        # disable upload button to prevent accidental double-click

        self.start_cf_progress_bar_pulse()

        self.log_color_print("Starting upload process")
        t = Thread(target=self._upload_to_server)
        t.daemon = True
        t.start()

    def handle_api_thread_error(self, function_name,
                                exception_error, error_msg,
                                uploaded_samples_q=None):

        """
        Subscribed to "handle_api_thread_error"
        Called by any api method when an error occurs
        It's set up this way because api is running
        in a different thread so the regular try-except block wasn't catching
        errors from this function

        writes all contents of uploaded_samples_q in to .miseqUploaderInfo
        file to enable resuming from upload at a later time

        arguments:
            exception_error -- Exception object
            error_msg -- message string to be displayed in log panel
            uploaded_samples_q -- Queue that contains strings of uploaded
                                sample IDs
                                it's self.uploaded_samples_q being passed back
                                from api.send_pair_sequence_files()
        no return value
        """

        if uploaded_samples_q is not None:
            uploaded_samples = []
            while not uploaded_samples_q.empty():
                uploaded_samples.append(uploaded_samples_q.get())

            self.mui_created_in_handle_api_thread_error = True

            self.create_miseq_uploader_info_file(uploaded_samples)

        # upload_id might not yet be set if the api error is from before
        # creating a sequencing run or the error is with the creation itself
        if self.curr_upload_id is not None:
            self.api.set_pair_seq_run_error(self.curr_upload_id)

        wx.CallAfter(self.pulse_timer.Stop)
        wx.CallAfter(
            self.display_warning, "From {fname}".format(fname=function_name) +
            " {error_name}: {error_msg}".format(
                error_name=exception_error.__name__,
                error_msg=error_msg),
            dlg_msg="API " + exception_error.__name__)

    def pair_seq_files_upload_complete(self):

        """
        Subscribed to message "pair_seq_files_upload_complete".
        This message is going to be sent by ApiCalls.send_pair_sequence_files()
        once all the sequence files have been uploaded.

        Adds to wx events queue: publisher send a message that uploading
        sequence files is complete
        """

        wx.CallAfter(pub.sendMessage,
                     "update_progress_bars", progress_data="Upload Complete")

    def pair_upload_callback(self, monitor):

        """
        callback function used by api.send_pair_sequence_files()
        makes the publisher (pub) send "update_progress_bars" message that
        contains progress percentage data whenever the percentage of the
        current file being uploaded changes.

        arguments:
            monitor -- an encoder.MultipartEncoderMonitor object
                       used for calculating and storing upload percentage data
                       It tracks percentage of overall upload progress
                        and percentage of current file upload progress.
                       the percentages are rounded to `ndigits` decimal place.

        no return value
        """

        ndigits = 4
        monitor.cf_upload_pct = (monitor.bytes_read /
                                 (monitor.len * 1.0))
        monitor.cf_upload_pct = round(monitor.cf_upload_pct, ndigits) * 100

        monitor.total_bytes_read += (monitor.bytes_read - monitor.prev_bytes)
        monitor.ov_upload_pct = (monitor.total_bytes_read /
                                 (monitor.size_of_all_seq_files * 1.0))
        monitor.ov_upload_pct = round(monitor.ov_upload_pct, ndigits) * 100

        for i in range(0, len(monitor.files)):
            file = monitor.files[i]
            monitor.files[i] = path.split(file)[1]

        progress_data = {
            "curr_file_upload_pct": monitor.cf_upload_pct,
            "overall_upload_pct": monitor.ov_upload_pct,
            "curr_files_uploading": "\n".join(monitor.files)
        }

        # only call update_progress_bars if one of the % values have changed
        # update estimated remaining time if one of the % values have changed
        if (monitor.prev_cf_pct != monitor.cf_upload_pct or
                monitor.prev_ov_pct != monitor.ov_upload_pct):
            wx.CallAfter(pub.sendMessage,
                         "update_progress_bars",
                         progress_data=progress_data)

            elapsed_time = round(time() - monitor.start_time)
            if elapsed_time > 0:

                # bytes
                upload_speed = (monitor.total_bytes_read / elapsed_time)

                ert = ceil(abs((monitor.size_of_all_seq_files -
                               monitor.total_bytes_read) / upload_speed))

                wx.CallAfter(pub.sendMessage,
                             "update_remaining_time",
                             upload_speed=upload_speed,
                             estimated_remaining_time=ert)

        monitor.prev_bytes = monitor.bytes_read
        monitor.prev_cf_pct = monitor.cf_upload_pct
        monitor.prev_ov_pct = monitor.ov_upload_pct

    def get_upload_speed_str(self, upload_speed):

        """
        Constructs upload speed string
        Converts the given upload_speed argument to the largest possible
        metric ((bytes, kilobytes, megabytes, ...) per second) rounded to
        two decimal places

        arguments:
            upload_speed -- float upload speed in bytes per second

        return upload speed string
        """

        metrics = [
            "B/s", "KB/s", "MB/s", "GB/s", "TB/s", "PB/s", "EB/s", "ZB/s"
        ]

        metric_count = 0
        while upload_speed >= 1024.0:
            upload_speed = upload_speed / 1024.0
            metric_count += 1

        upload_speed = round(upload_speed, 2)

        return str(upload_speed) + " " + metrics[metric_count]

    def get_ert_str(self, ert):

        """
        Constructs estimated remaining time string
        Converts the given ert argument to largest possible decimal time
        (seconds, minutes, hours, days)
        Seconds and minutes are rounded to one decimal because the second
        decimal isn't significant compared to hours or days
        Hours or days are rounded to two decimal places

        arguments:
            ert -- float estimated remaining time in seconds
                   must be >= 1

        returns estimated remaining time string
        """

        decimal_time = [
            (1, "seconds"), (60, "minutes"), (60, "hours"), (24, "days")
        ]

        for d in decimal_time:
            if ert >= d[0]:
                ert = ert / d[0]
                rep = d[1]
            else:
                break

        if rep == "minutes" or rep == "seconds":
            ert = int(round(ert))
        else:
            ert = round(ert, 2)

        if ert == 1:  # if value is 1 then remove "s" (e.g minutes to minute)
            rep = rep[:-1]

        return str(ert) + " " + rep

    def update_remaining_time(self, upload_speed, estimated_remaining_time):

        """
        Update the labels for upload speed and estimated remaining time.

        arguments:
            upload_speed -- float upload speed in bytes per second
            estimated_remaining_time -- float est remaining time in seconds
                                        must be >= 1

        no return value
        """

        upload_speed_str = self.get_upload_speed_str(upload_speed)
        estimated_remaining_time_str = self.get_ert_str(
            estimated_remaining_time)

        wx.CallAfter(self.ov_upload_label.SetLabel, upload_speed_str)
        wx.CallAfter(self.ov_est_time_label.SetLabel,
                     estimated_remaining_time_str)

        wx.CallAfter(self.Layout)

    def update_progress_bars(self, progress_data):

        """
        Subscribed to "update_progress_bars"
        This function is called when pub (publisher) sends the message
        "update_progress_bars"

        Updates boths progress bars and progress labels
        If progress_data is a string equal to "Upload Complete" then
        it calls handle_upload_complete() which displays the
        "Upload Complete" message in the log panel and
        re-enables the upload button.

        arguments:
            progress_data -- dictionary that holds data
                             to be used by the progress bars and labels

        no return value
        """

        if self.pulse_timer.IsRunning():
            self.pulse_timer.Stop()

        if (isinstance(progress_data, str) and
                progress_data == "Upload Complete"):
            self.handle_upload_complete()

        else:
            self.cf_progress_bar.SetValue(
                progress_data["curr_file_upload_pct"])
            self.cf_progress_label.SetLabel("{files}\n{pct}%".format(
                files=str(progress_data["curr_files_uploading"]),
                pct=str(progress_data["curr_file_upload_pct"])))

            if progress_data["overall_upload_pct"] > 100:
                progress_data["overall_upload_pct"] = 100
            self.ov_progress_bar.SetValue(progress_data
                                          ["overall_upload_pct"])
            self.ov_progress_label.SetLabel("\nOverall: {pct}%".format(
                pct=str(progress_data["overall_upload_pct"])))

    def handle_upload_complete(self):

        """
        function responsible for handling what happens after an upload
        of sequence files finishes
        makes api request to set SequencingRun's uploadStatus in to "Complete"
        displays "Upload Complete" to log panel.
        sets value for Estimated remainnig time to "Complete"
        """

        t = Thread(target=self.api.set_pair_seq_run_complete,
                   args=(self.curr_upload_id,))
        t.daemon = True
        t.start()

        self.upload_complete = True
        self.create_miseq_uploader_info_file("Complete")
        wx.CallAfter(self.log_color_print, "Upload complete\n",
                     self.LOG_PNL_OK_TXT_COLOR)
        wx.CallAfter(self.ov_est_time_label.SetLabel, "Complete")

        wx.CallAfter(self.Layout)

    def display_completion_cmd_msg(self, completion_cmd):

        wx.CallAfter(self.log_color_print,
                     "Executing completion command: " + completion_cmd)

    def create_miseq_uploader_info_file(self, upload_status):

        """
        creates a .miseqUploaderInfo file
        Contains Upload ID and Upload Status
        Upload ID is is the SequencingRun's identifier in IRIDA
        Upload Status will either be "Complete" or the last sequencing file
        that was uploaded.
        If there was an error with the upload then the last sequencing file
        uploaded will be written so that the program knows from which point to
        resume when the upload is restarted

        arguments:
            upload_status -- string that's either "Complete" or
                             string list of completed sequencing file path
                             uploads if upload was interrupted
                             used to know which files still need to be uploaded
                             when resuming upload

        no return value
        """

        filename = path.join(self.curr_seq_run.sample_sheet_dir,
                             ".miseqUploaderInfo")
        info = {
            "Upload ID": self.curr_upload_id,
            "Upload Status": upload_status
        }
        with open(filename, "wb") as writer:
            json.dump(info, writer)

    def handle_invalid_sheet_or_seq_file(self, msg):

        """
        disable GUI elements and reset variables when an error happens

        displays warning message for the given msg
        disables upload button - greyed out and unclickable
        progress bar and label are hidden
        progress bar percent counter is reset back to 0
        self.seq_run set to None

        arguments:
                msg -- message to display in warning dialog message box

        no return value
        """

        self.dir_box.SetBackgroundColour(self.INVALID_SAMPLESHEET_BG_COLOR)
        self.display_warning(msg)
        self.upload_button.Disable()

        self.cf_progress_label.Hide()
        self.cf_progress_bar.Hide()
        self.cf_progress_label.SetLabel(self.cf_init_label)
        self.cf_progress_bar.SetValue(0)

        self.ov_progress_label.Hide()
        self.ov_upload_static_label.Hide()
        self.ov_upload_label.Hide()
        self.ov_est_time_static_label.Hide()
        self.ov_est_time_label.Hide()
        self.ov_progress_bar.Hide()
        self.ov_progress_label.SetLabel(self.ov_init_label)
        self.ov_upload_static_label.SetLabel(self.ov_upload_init_static_label)
        self.ov_upload_label.SetLabel(self.ov_upload_init_label)
        self.ov_est_time_static_label.SetLabel(
            self.ov_est_time_init_static_label)
        self.ov_est_time_label.SetLabel(self.ov_est_time_init_label)
        self.ov_progress_bar.SetValue(0)

        self.seq_run = None

    def open_dir_dlg(self, event):

        """
        Function bound to browseButton being clicked and dir_box being
            clicked or tabbbed/focused
        Opens dir dialog for user to select directory containing
            SampleSheet.csv
        Validates the found SampleSheet.csv
        If it's valid then proceed to create the sequence run (create_seq_run)
        else displays warning messagebox containing the error(s)

        arguments:
            event -- EVT_BUTTON when browse button is clicked
                    or EVT_SET_FOCUS when dir_box is focused via tabbing
                    or EVT_LEFT_DOWN when dir_box is clicked

        no return value
        """

        self.browse_button.SetFocus()

        self.dir_dlg = MDD(
            self, "Select directory containing Samplesheet.csv",
            defaultPath=path.dirname(self.browse_path),
            agwStyle=wx.lib.agw.multidirdialog.DD_DIR_MUST_EXIST)
        # agwStyle to disable "Create new folder"
        if self.dir_dlg.ShowModal() == wx.ID_OK:

            selected_directory = self.dir_dlg.GetPaths()[0]
            # unabashedly stolen from AnyBackup, where they reported something
            # similar here: http://sourceforge.net/p/anybackup/tickets/136/
            if (selected_directory.find("(") > -1):
                # Basically: with wx3 and Windows, the drive label gets
                # inserted into the value returned by GetPaths(), so this
                # strips out the label.
                selected_directory = re.sub('.*\(', '', selected_directory)
                selected_directory = selected_directory.replace(')', '')
                self.browse_path = selected_directory.strip(sep)
            elif selected_directory.find("Home directory") > -1:
                # wxWidgets (in GTK2.0) tries to place a friendly
                # "Home Directory" and "Desktop" entry in the file chooser.
                # Calling "GetPaths" from wxPython ultimately asks for
                # `GetItemText` on a `TreeCtrl` object, when it should really
                # be interrogating `GetItemData` and asking for the path. This
                # is reported at http://trac.wxwidgets.org/ticket/17190
                home_dir = path.expanduser("~")
                self.browse_path = selected_directory.replace("Home directory",
                                                              home_dir)
            else:
                # On non-Windows hosts the drive label doesn't show up, so just
                # use whatever is selected.
                self.browse_path = selected_directory

            self.start_sample_sheet_processing()

        self.dir_dlg.Destroy()

    def start_sample_sheet_processing(self, first_start=False):

        """
        first_start is an optional argument to pass to start_sample_sheet_processing
        to prevent it from showing an unexpected error message on startup if the
        default directory does not have any sample sheets within it.
        """
        self.dir_box.SetValue(self.browse_path)
        self.cf_progress_label.SetLabel(self.cf_init_label)
        self.cf_progress_bar.SetValue(0)
        self.ov_progress_label.SetLabel(self.ov_init_label)

        self.ov_upload_static_label.SetLabel(self.ov_upload_init_static_label)
        self.ov_upload_label.SetLabel(self.ov_upload_init_label)
        self.ov_est_time_static_label.SetLabel(
            self.ov_est_time_init_static_label)
        self.ov_est_time_label.SetLabel(self.ov_est_time_init_label)

        self.ov_progress_bar.SetValue(0)

        # clear the list of sequencing runs and list of samplesheets when user
        # selects a new directory
        self.seq_run_list = []
        self.sample_sheet_files = []

        try:

            ss_list = self.find_sample_sheet(self.browse_path,
                                             "SampleSheet.csv")

            if len(ss_list) == 0:
                sub_dirs = [str(f) for f in listdir(self.browse_path)
                            if path.isdir(
                            path.join(self.browse_path, f))]

                err_msg = ("SampleSheet.csv file not found in the " +
                           "selected directory:\n" +
                           self.browse_path)
                if len(sub_dirs) > 0:
                    err_msg = (err_msg + " or its " +
                               "subdirectories:\n" + ", ".join(sub_dirs))
                # Supress any error messages if the application is just starting up
                if not first_start:
                    raise SampleSheetError(err_msg)

            else:

                pruned_list = (
                    self.prune_sample_sheets_check_miseqUploaderInfo(
                        ss_list))
                if len(pruned_list) == 0:
                    err_msg = (
                        "The following have already been uploaded:\n" +
                        "{_dir}").format(_dir=",\n".join(ss_list))
                    raise SampleSheetError(err_msg)

                self.sample_sheet_files = pruned_list

                for ss in self.sample_sheet_files:
                    self.log_color_print("Processing: " + ss)
                    try:
                        self.process_sample_sheet(ss)
                    except (SampleSheetError, SequenceFileError):
                        self.log_color_print(
                            "Stopping the processing of SampleSheet.csv " +
                            "files due to failed validation of previous " +
                            "file: " + ss + "\n",
                            self.LOG_PNL_ERR_TXT_COLOR)
                        self.sample_sheet_files = []
                        break  # stop processing sheets if validation fails

        except (SampleSheetError, OSError, IOError), e:
            self.handle_invalid_sheet_or_seq_file(str(e))

        if len(self.sample_sheet_files) > 0:
            self.log_color_print("List of SampleSheet files to be uploaded:")
            for ss_file in self.sample_sheet_files:
                self.log_color_print(ss_file)
            self.log_color_print("\n")

    def process_sample_sheet(self, sample_sheet_file):

        """
        validate samplesheet file and then tries to create a sequence run
        raises errors if
            samplesheet is not valid
            failed to create sequence run (SequenceFileError)

        arguments:
            sample_sheet_file -- full path of SampleSheet.csv
        """

        v_res = validate_sample_sheet(sample_sheet_file)

        if v_res.is_valid():
            self.dir_box.SetBackgroundColour(self.VALID_SAMPLESHEET_BG_COLOR)

            try:
                self.create_seq_run(sample_sheet_file)

                self.upload_button.Enable()
                self.log_color_print(sample_sheet_file + " is valid\n",
                                     self.LOG_PNL_OK_TXT_COLOR)
                self.cf_progress_label.Show()
                self.cf_progress_bar.Show()
                self.ov_progress_label.Show()
                self.ov_upload_static_label.Show()
                self.ov_upload_label.Show()
                self.ov_est_time_static_label.Show()
                self.ov_est_time_label.Show()
                self.ov_progress_bar.Show()
                self.Layout()

            except (SampleSheetError, SequenceFileError), e:
                self.handle_invalid_sheet_or_seq_file(str(e))
                raise

        else:
            self.handle_invalid_sheet_or_seq_file(v_res.get_errors())
            raise SampleSheetError

    def find_sample_sheet(self, top_dir, ss_pattern):

        """
        Traverse through a directory and a level below it searching for
            a file that matches the given SampleSheet pattern.

        arguments:
            top_dir -- top level directory to start searching from
            ss_pattern -- SampleSheet pattern to try and match
                          using fnfilter/ fnmatch.filter

        returns list containing files that match pattern
        """

        result_list = []

        if path.isdir(top_dir):
            for root, dirs, files in walk(top_dir):
                for filename in fnfilter(files, ss_pattern):
                    result_list.append(path.join(root, filename))

        return result_list

    def prune_sample_sheets_check_miseqUploaderInfo(self, ss_list):

        """
        check if a .miseqUploaderInfo file exists in a directory
          if it does then check the Upload Status inside the file

          if it's "Complete" (i.e the folder has already been uploaded) then
          remove it from the corresponding SampleSheet.csv in ss_list.

          if it's not then that means the previous attempt at uploading
          the SampleSheet.csv was interrupted and we need to resume the upload.

          In this case Upload Status will contain a list of sample ID's that
          have been already uploaded. This data will be loaded in to
          self.prev_uploaded_samples and the previous upload_id will be
          loaded in to self.loaded_upload_id.

        else if a .miseqUploaderComplete file exists in a directory then
        remove it from the corresponding SampleSheet.csv file path in ss_list

        argument:
            ss_list -- list containing path to SampleSheet.csv files

        ss_list

        return ss_list just to be explicit
        """

        pruned_list = deepcopy(ss_list)

        for _dir in map(path.dirname, pruned_list[:]):
            if ".miseqUploaderInfo" in listdir(_dir):
                uploader_info_filename = path.join(_dir, ".miseqUploaderInfo")
                with open(uploader_info_filename, "rb") as reader:
                    info = json.load(reader)

                    if info["Upload Status"] == "Complete":
                        pruned_list.remove(path.join(_dir, "SampleSheet.csv"))
                    else:
                        self.prev_uploaded_samples = info["Upload Status"]
                        self.loaded_upload_id = info["Upload ID"]

            elif ".miseqUploaderComplete" in listdir(_dir):
                pruned_list.remove(path.join(_dir, "SampleSheet.csv"))

        return pruned_list

    def create_seq_run(self, sample_sheet_file):

        """
        Try to create a SequencingRun object and add it to self.seq_run_list
        Parses out the metadata dictionary and sampleslist from selected
            sample_sheet_file
        raises errors:
                if parsing raises/throws Exceptions
                if the parsed out samplesList fails validation
                if a pair file for a sample in samplesList fails validation
        these errors are expected to be caught by the calling function
            open_dir_dlg and it will be the one sending them to display_warning

        no return value
        """

        try:
            m_dict = parse_metadata(sample_sheet_file)
            s_list = complete_parse_samples(sample_sheet_file)

        except SequenceFileError, e:
            raise SequenceFileError(str(e))

        except SampleSheetError, e:
            raise SampleSheetError(str(e))

        v_res = validate_sample_list(s_list)
        if v_res.is_valid():

            seq_run = SequencingRun()
            seq_run.set_metadata(m_dict)
            seq_run.set_sample_list(s_list)
            seq_run.sample_sheet_dir = path.dirname(sample_sheet_file)
            seq_run.sample_sheet_file = sample_sheet_file

        else:
            raise SequenceFileError(v_res.get_errors())

        for sample in seq_run.get_sample_list():
            pf_list = seq_run.get_pair_files(sample.get_id())
            v_res = validate_pair_files(pf_list, sample.get_id())
            if v_res.is_valid() is False:
                raise SequenceFileError(v_res.get_errors())

        self.seq_run_list.append(seq_run)

    def set_updated_api(self, api):

        """
        Subscribed to message "set_updated_api".
        This message is sent by SettingsPanel.close_handler().
        When SettingsPanel is closed update self.api to equal the newly created
        ApiCalls object from SettingsPanel

        if the updated self.api is not None re-enable the upload button

        reload self.conf_parser in case it's value (e.g completion_cmd)
        gets updated

        no return value
        """

        self.api = api
        if self.api is not None:
            self.upload_button.Enable()

        self.conf_parser.read(self.config_file)


class MainFrame(wx.Frame):

    def __init__(self, parent=None):

        self.parent = parent
        self.display_size = wx.GetDisplaySize()
        self.num_of_monitors = wx.Display_GetCount()

        WIDTH_PCT = 0.85
        HEIGHT_PCT = 0.75
        self.WINDOW_SIZE_WIDTH = (
            self.display_size.x/self.num_of_monitors) * WIDTH_PCT
        self.WINDOW_SIZE_HEIGHT = (self.display_size.y) * HEIGHT_PCT

        self.WINDOW_MAX_WIDTH = 900
        self.WINDOW_MAX_HEIGHT = 800
        self.MIN_WIDTH_SIZE = 600
        self.MIN_HEIGHT_SIZE = 400
        if self.WINDOW_SIZE_WIDTH > self.WINDOW_MAX_WIDTH:
            self.WINDOW_SIZE_WIDTH = self.WINDOW_MAX_WIDTH
        if self.WINDOW_SIZE_HEIGHT > self.WINDOW_MAX_HEIGHT:
            self.WINDOW_SIZE_HEIGHT = self.WINDOW_MAX_HEIGHT

        self.WINDOW_SIZE = (self.WINDOW_SIZE_WIDTH, self.WINDOW_SIZE_HEIGHT)

        wx.Frame.__init__(self, parent=self.parent, id=wx.ID_ANY,
                          title="IRIDA Uploader",
                          size=self.WINDOW_SIZE,
                          style=wx.DEFAULT_FRAME_STYLE)

        self.OPEN_SETTINGS_ID = 111  # arbitrary value
        self.OPEN_DOCS_ID = 222  # arbitrary value

        self.mp = MainPanel(self)
        self.settings_frame = self.mp.settings_frame

        img_dir_path = path.join(path_to_module, "images")
        self.icon = wx.Icon(path.join(img_dir_path, "iu.ico"),
                            wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)

        self.add_options_menu()
        self.add_settings_option()
        self.add_documentation_option()

        self.SetSizeHints(self.MIN_WIDTH_SIZE, self.MIN_HEIGHT_SIZE,
                          self.WINDOW_MAX_WIDTH, self.WINDOW_MAX_HEIGHT)
        self.Bind(wx.EVT_CLOSE, self.mp.close_handler)
        self.Center()

    def add_options_menu(self):

        """
        Adds Options menu on top of program
        Shortcut / accelerator: Alt + T

        no return value
        """

        self.menubar = wx.MenuBar()
        self.options_menu = wx.Menu()
        self.menubar.Append(self.options_menu, "Op&tions")
        self.SetMenuBar(self.menubar)

    def add_settings_option(self):

        """
        Add Settings on options menu
        Clicking Settings will call self.open_settings()
        Shortcut / accelerator: (Alt + T) + S or (CTRL + I)

        no return value
        """

        self.settings_menu_item = wx.MenuItem(self.options_menu,
                                              self.OPEN_SETTINGS_ID,
                                              "&Settings\tCTRL+I")
        self.options_menu.AppendItem(self.settings_menu_item)
        self.Bind(wx.EVT_MENU, self.open_settings, id=self.OPEN_SETTINGS_ID)

    def open_settings(self, evt):

        """
        Open the settings menu(SettingsFrame)

        no return value
        """

        self.settings_frame.Center()
        self.settings_frame.Show()

    def add_documentation_option(self):

        """
        Adds Documentation on options menu
        Clicking Documentation will call self.open_docs()
        Accelerator: ALT + T + D

        no return value
        """

        self.docs_menu_item = wx.MenuItem(self.options_menu,
                                          self.OPEN_DOCS_ID,
                                          "&Documentation")
        self.options_menu.AppendItem(self.docs_menu_item)
        self.Bind(wx.EVT_MENU, self.open_docs, id=self.OPEN_DOCS_ID)

    def open_docs(self, evt):

        """
        Open documentation with user's default browser

        no return value
        """
        docs_path = path.join(path_to_module, "..", "..", "html",
                              "index.html")
        if not path.isfile(docs_path):
            wx.CallAfter(self.display_warning, "Documentation is not built.")
        else:
            wx.CallAfter(webbrowser.open, docs_path)


def check_config_dirs(conf_parser):
    """
    Checks to see if the config directories are set up for this user. Will
    create the user config directory and copy a default config file if they
    do not exist

    no return value
    """

    if not path.exists(user_config_dir):
        print "User config dir doesn't exist, making new one."
        makedirs(user_config_dir)

    if not path.exists(user_config_file):
        # find the default config dir from (at least) two directory levels
        # above this directory
        conf_file = find("config.conf", path.join(path_to_module, "..", ".."))

        print "User config file doesn't exist, using defaults."
        copy2(conf_file, user_config_dir)

        conf_parser.read(conf_file)


def find(name, start_dir):
    """
    Find a file by name in the given path


    return the file (if found) otherwise undef
    """
    for root, dirs, files in walk(start_dir):
        if name in files:
            return path.join(root, name)


def main():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    frame.mp.api = frame.settings_frame.attempt_connect_to_api()
    app.MainLoop()

if __name__ == "__main__":
    main()
