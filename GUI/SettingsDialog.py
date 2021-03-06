# coding: utf-8

import wx
import os
import logging
import threading
import types

from API.pubsub import send_message
from API.APIConnector import APIConnectorTopics, connect_to_irida
from API.config import read_config_option, write_config_option
from wx.lib.pubsub import pub
from os import path
from GUI.ProcessingPlaceholderText import ProcessingPlaceholderText

class URLEntryPanel(wx.Panel):
    """Panel for allowing entry of a URL"""
    def __init__(self, parent=None, default_url=""):
        wx.Panel.__init__(self, parent)
        self._sizer = wx.BoxSizer(wx.HORIZONTAL)

        self._url = wx.TextCtrl(self)
        self._url.Bind(wx.EVT_KILL_FOCUS, self._field_changed)
        self._url.SetValue(default_url)

        self._status_label = ProcessingPlaceholderText(self)

        label = wx.StaticText(self, label="Server URL")
        label.SetToolTipString("URL for the IRIDA server API.")
        self._sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5, proportion=0)
        self._sizer.Add(self._url, flag=wx.EXPAND, proportion=1)
        self._sizer.Add(self._status_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=5, proportion=0)

        self.SetSizerAndFit(self._sizer)
        self.Layout()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        pub.subscribe(self._status_label.SetError, APIConnectorTopics.connection_error_url_topic)
        pub.subscribe(self._status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.subscribe(self._status_label.SetSuccess, APIConnectorTopics.connection_success_valid_url)

    def _on_close(self, evt=None):
        pub.unsubscribe(self._status_label.SetError, APIConnectorTopics.connection_error_url_topic)
        pub.unsubscribe(self._status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.unsubscribe(self._status_label.SetSuccess, APIConnectorTopics.connection_success_valid_url)

    def _field_changed(self, evt=None):
        send_message(SettingsDialog.field_changed_topic, field_name="baseurl", field_value=self._url.GetValue())
        self._status_label.Restart()
        evt.Skip()

class UserDetailsPanel(wx.Panel):
    """Panel for allowing entry of user credentials"""
    def __init__(self, parent=None, default_user="", default_pass=""):
        wx.Panel.__init__(self, parent)
        border = wx.StaticBox(self, label="User authorization")
        sizer = wx.StaticBoxSizer(border, wx.VERTICAL)
        self._status_label_user = ProcessingPlaceholderText(self)
        self._status_label_pass = ProcessingPlaceholderText(self)

        username_sizer = wx.BoxSizer(wx.VERTICAL)
        username_label = wx.StaticText(self, label="Username")
        username_label.SetToolTipString("Your IRIDA username")
        username_sizer.Add(username_label, flag=wx.EXPAND | wx.BOTTOM, border=2)

        username_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._username = wx.TextCtrl(self)
        self._username.Bind(wx.EVT_KILL_FOCUS, self._username_changed)
        self._username.SetValue(default_user)
        username_input_sizer.Add(self._username, flag=wx.EXPAND, proportion=1)
        username_input_sizer.Add(self._status_label_user, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=5, proportion=0)
        username_sizer.Add(username_input_sizer, flag=wx.EXPAND)
        sizer.Add(username_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        password_sizer = wx.BoxSizer(wx.VERTICAL)
        password_label = wx.StaticText(self, label="Password")
        password_label.SetToolTipString("Your IRIDA password")
        password_sizer.Add(password_label, flag=wx.EXPAND | wx.BOTTOM, border=2)

        password_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._password = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self._password.Bind(wx.EVT_KILL_FOCUS, self._password_changed)
        self._password.SetValue(default_pass)
        password_input_sizer.Add(self._password, flag=wx.EXPAND, proportion=1)
        password_input_sizer.Add(self._status_label_pass, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=5, proportion=0)
        password_sizer.Add(password_input_sizer, flag=wx.EXPAND)
        sizer.Add(password_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        self.SetSizerAndFit(sizer)
        self.Layout()

        pub.subscribe(self._handle_connection_error, APIConnectorTopics.connection_error_user_credentials_topic)
        pub.subscribe(self._status_label_user.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.subscribe(self._status_label_pass.SetSuccess, APIConnectorTopics.connection_success_topic)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, evt=None):
        pub.unsubscribe(self._handle_connection_error, APIConnectorTopics.connection_error_user_credentials_topic)
        pub.unsubscribe(self._status_label_user.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.unsubscribe(self._status_label_pass.SetSuccess, APIConnectorTopics.connection_success_topic)

    def _username_changed(self, evt=None):
        send_message(SettingsDialog.field_changed_topic, field_name="username", field_value=self._username.GetValue())
        self._status_label_user.Restart()
        evt.Skip()

    def _password_changed(self, evt=None):
        send_message(SettingsDialog.field_changed_topic, field_name="password", field_value=self._password.GetValue())
        self._status_label_pass.Restart()
        evt.Skip()

    def _handle_connection_error(self, error_message=None):
        self._status_label_user.SetError(error_message)
        self._status_label_pass.SetError(error_message)

class ClientDetailsPanel(wx.Panel):
    """Panel for allowing entry of client credentials"""
    def __init__(self, parent=None, default_client_id="", default_client_secret=""):
        wx.Panel.__init__(self, parent)
        border = wx.StaticBox(self, label="Client authorization")
        sizer = wx.StaticBoxSizer(border, wx.VERTICAL)
        self._client_id_status_label = ProcessingPlaceholderText(self)
        self._client_secret_status_label = ProcessingPlaceholderText(self)

        client_id_sizer = wx.BoxSizer(wx.VERTICAL)
        client_id_label = wx.StaticText(self, label="Client ID")
        client_id_label.SetToolTipString("Your IRIDA client ID")
        client_id_sizer.Add(client_id_label, flag=wx.EXPAND | wx.BOTTOM, border=2)

        client_id_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._client_id = wx.TextCtrl(self)
        self._client_id.Bind(wx.EVT_KILL_FOCUS, self._client_id_changed)
        self._client_id.SetValue(default_client_id)
        client_id_input_sizer.Add(self._client_id, flag=wx.EXPAND, proportion=1)
        client_id_input_sizer.Add(self._client_id_status_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=5, proportion=0)
        client_id_sizer.Add(client_id_input_sizer, flag=wx.EXPAND)
        sizer.Add(client_id_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        client_secret_sizer = wx.BoxSizer(wx.VERTICAL)
        client_secret_label = wx.StaticText(self, label="Client Secret")
        client_secret_label.SetToolTipString("Your IRIDA client secret")
        client_secret_sizer.Add(client_secret_label, flag=wx.EXPAND | wx.BOTTOM, border=2)

        client_secret_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._client_secret = wx.TextCtrl(self)
        self._client_secret.Bind(wx.EVT_KILL_FOCUS, self._client_secret_changed)
        self._client_secret.SetValue(default_client_secret)
        client_secret_input_sizer.Add(self._client_secret, flag=wx.EXPAND, proportion=1)
        client_secret_input_sizer.Add(self._client_secret_status_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, border=5, proportion=0)
        client_secret_sizer.Add(client_secret_input_sizer, flag=wx.EXPAND)
        sizer.Add(client_secret_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        self.SetSizerAndFit(sizer)
        self.Layout()

        pub.subscribe(self._client_id_status_label.SetError, APIConnectorTopics.connection_error_client_id_topic)
        pub.subscribe(self._client_secret_status_label.SetError, APIConnectorTopics.connection_error_client_secret_topic)
        pub.subscribe(self._client_id_status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.subscribe(self._client_secret_status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.subscribe(self._client_id_status_label.SetSuccess, APIConnectorTopics.connection_success_valid_client_id)
        pub.subscribe(self._client_secret_status_label.SetSuccess, APIConnectorTopics.connection_success_valid_client_secret)

        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, evt=None):
        pub.unsubscribe(self._client_id_status_label.SetError, APIConnectorTopics.connection_error_client_id_topic)
        pub.unsubscribe(self._client_secret_status_label.SetError, APIConnectorTopics.connection_error_client_secret_topic)
        pub.unsubscribe(self._client_id_status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.unsubscribe(self._client_secret_status_label.SetSuccess, APIConnectorTopics.connection_success_topic)
        pub.unsubscribe(self._client_id_status_label.SetSuccess, APIConnectorTopics.connection_success_valid_client_id)
        pub.unsubscribe(self._client_secret_status_label.SetSuccess, APIConnectorTopics.connection_success_valid_client_secret)

    def _client_id_changed(self, evt=None):
        send_message(SettingsDialog.field_changed_topic, field_name="client_id", field_value=self._client_id.GetValue())
        self._client_id_status_label.Restart()
        evt.Skip()

    def _client_secret_changed(self, evt=None):
        send_message(SettingsDialog.field_changed_topic, field_name="client_secret", field_value=self._client_secret.GetValue())
        self._client_secret_status_label.Restart()
        evt.Skip()

class PostProcessingTaskPanel(wx.Panel):
    """Panel for allowing entry of a post-processing task."""
    def __init__(self, parent=None, default_post_process=""):
        wx.Panel.__init__(self, parent)
        self._sizer = wx.BoxSizer(wx.HORIZONTAL)

        task_label = wx.StaticText(self, label="Task to run on successful upload")
        task_label.SetToolTipString("Post-processing job to run after a run has been successfully uploaded to IRIDA.")
        self._sizer.Add(task_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5, proportion=0)

        task = wx.TextCtrl(self)
        task.Bind(wx.EVT_KILL_FOCUS, lambda evt: send_message(SettingsDialog.field_changed_topic, field_name="completion_cmd", field_value=task.GetValue()))
        task.SetValue(default_post_process)
        self._sizer.Add(task, flag=wx.EXPAND, proportion=1)

        self.SetSizerAndFit(self._sizer)
        self.Layout()

class DefaultDirectoryPanel(wx.Panel):
    """Panel for selecting a default directory for auto scanning."""
    def __init__(self, parent=None, default_directory="", monitor_directory=False):
        wx.Panel.__init__(self, parent)
        self._sizer = wx.BoxSizer(wx.HORIZONTAL)

        directory_label = wx.StaticText(self, label="Default directory")
        directory_label.SetToolTipString("Default directory to scan for uploads")
        self._sizer.Add(directory_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5, proportion=0)

        directory = wx.DirPickerCtrl(self, path=default_directory)
        self.Bind(wx.EVT_DIRPICKER_CHANGED, lambda evt: send_message(SettingsDialog.field_changed_topic, field_name="default_dir", field_value=directory.GetPath()))
        self._sizer.Add(directory, flag=wx.EXPAND, proportion=1)

        monitor_checkbox = wx.CheckBox(self, label="Monitor directory for new runs?")
        monitor_checkbox.SetValue(monitor_directory)
        monitor_checkbox.SetToolTipString("Monitor the default directory for when the Illumina Software indicates that the analysis is complete and ready to upload (when CompletedJobInfo.xml is written to the directory).")
        monitor_checkbox.Bind(wx.EVT_CHECKBOX, lambda evt: send_message(SettingsDialog.field_changed_topic, field_name="monitor_default_dir", field_value=str(monitor_checkbox.GetValue())))
        self._sizer.Add(monitor_checkbox, flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=5, proportion=0)

        self.SetSizerAndFit(self._sizer)
        self.Layout()

class SettingsDialog(wx.Dialog):
    field_changed_topic = "settings.field_changed_topic"
    settings_closed_topic = "settings.settings_closed_topic"

    """The settings frame is where the user can configure user-configurable settings."""
    def __init__(self, parent=None, first_run=False):
        wx.Dialog.__init__(self, parent, title="Settings", style=wx.DEFAULT_DIALOG_STYLE)
        self._first_run = first_run
        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self._defaults = {}

        self._sizer.Add(URLEntryPanel(self, default_url=read_config_option("baseurl")), flag=wx.EXPAND | wx.ALL, border=5)

        authorization_sizer = wx.BoxSizer(wx.HORIZONTAL)
        authorization_sizer.Add(ClientDetailsPanel(self, default_client_id=read_config_option("client_id"), default_client_secret=read_config_option("client_secret")), flag=wx.EXPAND | wx.RIGHT, border=2, proportion=1)
        authorization_sizer.Add(UserDetailsPanel(self, default_user=read_config_option("username"), default_pass=read_config_option("password")), flag=wx.EXPAND | wx.LEFT, border=2, proportion=1)
        self._sizer.Add(authorization_sizer, flag=wx.EXPAND | wx.ALL, border=5)

        self._sizer.Add(PostProcessingTaskPanel(self, default_post_process=read_config_option("completion_cmd")), flag=wx.EXPAND | wx.ALL, border=5)
        self._sizer.Add(DefaultDirectoryPanel(self, default_directory=read_config_option("default_dir"), monitor_directory=read_config_option("monitor_default_dir", expected_type=bool)), flag=wx.EXPAND | wx.ALL, border=5)

        self._sizer.Add(self.CreateSeparatedButtonSizer(flags=wx.OK), flag=wx.EXPAND | wx.ALL, border=5)

        self.SetSizerAndFit(self._sizer)
        self.Layout()

        pub.subscribe(self._field_changed, SettingsDialog.field_changed_topic)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_BUTTON, self._on_close, id=wx.ID_OK)
        threading.Thread(target=connect_to_irida).start()

    def _on_close(self, evt=None):
        pub.unsubscribe(self._field_changed, SettingsDialog.field_changed_topic)
        # only inform the UI that settings have changed if we're not being invoked
        # to set up the initial configuration settings (i.e., the first run)
        if type(evt) is wx.CommandEvent and not self._first_run:
            logging.info("Closing settings dialog and informing UI to scan for sample sheets.")
            send_message(SettingsDialog.settings_closed_topic)
        evt.Skip()

    def _field_changed(self, field_name, field_value, attempt_connect=True):
        """A field change has been detected, write it out to the config file.

        Args:
            field_name: the field name that was changed.
            field_value: the current value of the field to write out.
            attempt_connect: if an attempt should be made to connect to IRIDA after
                writing out the value to the config file.
        """
        logging.info("Saving changes {field_name} -> {field_value}".format(field_name=field_name, field_value=field_value))
        write_config_option(field_name, field_value)

        if attempt_connect:
            threading.Thread(target=connect_to_irida).start()
