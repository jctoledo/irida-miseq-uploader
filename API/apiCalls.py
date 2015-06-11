import ast
import json
import httplib
import sys
sys.path.append("../")
from os import path
from urllib2 import Request, urlopen, URLError, HTTPError
from urlparse import urljoin
from ConfigParser import RawConfigParser

from rauth import OAuth2Service, OAuth2Session
from requests import Request
from requests.exceptions import HTTPError as request_HTTPError

from Model.SequenceFile import SequenceFile
from Model.Project import Project
from Model.Sample import Sample
from Model.ValidationResult import ValidationResult
from Exceptions.ProjectError import ProjectError
from Exceptions.SampleError import SampleError
from Validation.offlineValidation import validateURLForm as validate_URL_Form


class ApiCalls:

    def __init__(self, client_id, client_secret,
                base_URL, username, password, max_wait_time=20):
        """
        Create OAuth2Session and store it

        arguments:
            client_id -- client_id for creating access token. Found in iridaUploader/config.conf
            client_secret -- client_secret for creating access token. Found in iridaUploader/config.conf
            base_URL -- url of the IRIDA server
            username -- username for server
            password -- password for given username

        return ApiCalls object
        """

        self.client_id = client_id
        self.client_secret = client_secret
        self.base_URL = base_URL
        self.username = username
        self.password = password
        self.max_wait_time = max_wait_time

        self.create_session()

    def create_session(self):

        """
        create session to be re-used until expiry for get and post calls

        returns session (OAuth2Session object)
        """

        if self.base_URL[-1:] != "/":
            self.base_URL = self.base_URL + "/"

        if validate_URL_Form(self.base_URL):
            oauth_service = self.get_oauth_service()
            access_token = self.get_access_token(oauth_service)
            self.session = oauth_service.get_session(access_token)

            if self.validate_URL_existence(self.base_URL, use_session=True)==False:
                raise Exception("Cannot create session. Verify your credentials are correct.")

        else:
            raise URLError(self.base_URL + " is not a valid URL")

    def get_oauth_service(self):

        """
        get oauth service to be used to get access token

        returns oauthService
        """

        access_token_url = urljoin(self.base_URL, "oauth/token")
        oauth_serv = OAuth2Service(
            client_id=client_id,
            client_secret=client_secret,
            name="irida",
            access_token_url=access_token_url,
            base_url=self.base_URL
        )

        return oauth_serv

    def get_access_token(self, oauth_service):

        """
        get access token to be used to get session from oauth_service

        arguments:
            oauth_service -- O2AuthService from get_oauth_service

        returns access token
        """

        params = {
            "data" : {
                "grant_type":"password",
                "client_id":client_id,
                "client_secret":client_secret,
                "username":self.username,
                "password":self.password
            }
        }

        access_token = oauth_service.get_access_token(decoder=self.decoder,**params)

        return access_token

    def decoder(self, return_dict):

        """
        safely parse given dictionary

        arguments:
            return_dict -- access token dictionary

        returns evaluated dictionary
        """

        irida_dict = ast.literal_eval(return_dict)
        return irida_dict

    def validate_URL_existence(self, url, use_session=False):

        """
        tries to validate existence of given url by trying to open it.
        true if HTTP OK, false if HTTP NOT FOUND otherwise raises error containing error code and message

        arguments:
            url -- the url link to open and validate
            use_session -- if True then this uses self.session.get(url) instead of urlopen(url) to get response

        returns
            true if http response OK 200
            false if http response NOT FOUND 404
        """

        if use_session == True:
            response = self.session.get(url)

            if response.status_code == httplib.OK:
                return True
            elif response.status_code == httplib.NOT_FOUND:
                return False
            else:
                raise Exception(str(response.status_code) + " " + response.reason)

        else:
            response = urlopen(url, timeout=self.max_wait_time)

            if response.code == httplib.OK:
                return True
            elif response.code == httplib.NOT_FOUND:
                return False
            else:
                raise Exception(str(response.code) + " " + response.msg)


    def get_link(self, targ_url, target_key, targ_dict=""):

        """
        makes a call to targ_url(api) expecting a json response
        tries to retrieve target_key from response to find link to that resource
        raises exceptions if target_key not found or targ_url is invalid

        arguments:
            targ_url -- URL to retrieve link from
            target_key -- name of link (e.g projects or project/samples)
            targ_dict -- optional dict containing key and value to search for in targets.
            (e.g {key="identifier",value="100"} to retrieve where identifier=100 )

        returns link if it exists
        """

        retVal=None

        if self.validate_URL_existence(targ_url, use_session=True):
            response = self.session.get(targ_url)

            if len(targ_dict)>0:
                resources_List = response.json()["resource"]["resources"]
                try:
                    links_list = next(resource["links"] for resource in resources_List
                                if resource[targ_dict["key"]] == targ_dict["value"])

                except KeyError:
                    raise KeyError(targ_dict["key"] + " not found." +
                                    "Available keys:" + resource.keys())

                except StopIteration:
                    raise KeyError(targ_dict["value"] + " not found.")

            else:
                links_list = response.json()["resource"]["links"]
            try:
                retVal = next(link["href"] for link in links_list
                        if link["rel"] == target_key)

            except StopIteration:
                raise KeyError(target_key + " not found in links. " +
                "Available links: " +
                ",".join([ str(link["rel"]) for link in links_list]))

        else:
            raise request_HTTPError("Error: " +
                                    targ_url + " is not a valid URL")

        return retVal

    def get_projects(self):

        """
        API call to api/projects to get list of projects

        returns list containing projects. each project is Project object.
        """

        url = self.get_link(self.base_URL, "projects")
        response = self.session.get(url)

        result = response.json()["resource"]["resources"]
        project_list = [
            Project(
                projDict["name"],
                projDict["projectDescription"],
                projDict["identifier"]
            )
            for projDict in result
        ]

        return project_list

    def get_samples(self, project):

        """
        API call to api/projects/project_id/samples

        arguments:
            project -- a Project object used to get project_id

        returns list of samples for the given project. each sample is a Sample object.
        """

        project_id = project.getID()

        try:
            proj_URL = self.get_link(self.base_URL, "projects")
            url = self.get_link(proj_URL, "project/samples",
                                targ_dict={
                                    "key":"identifier",
                                    "value":project_id
                                })

        except StopIteration:
            raise ProjectError("The given project ID: " +
                                project_id +" doesn't exist")

        response = self.session.get(url)
        result = response.json()["resource"]["resources"]
        sample_list = [Sample(sample_dict) for sample_dict in result]

        return sample_list


    def get_sequence_files(self, project, sample):

        """
        API call to api/projects/project_id/sample_id/sequenceFiles

        arguments:
            project -- a Project object used to get project_id
            sample -- a Sample object used to get sample_id


        returns list of sequencefile dictionary for given sample_id
        """

        project_id = project.getID()
        sample_id = sample.getID()

        try:
            proj_URL = self.get_link(self.base_URL, "projects")
            sample_URL = self.get_link(proj_URL, "project/samples",
                                        targ_dict={
                                            "key":"identifier",
                                            "value":project_id
                                        })

        except StopIteration:
            raise ProjectError("The given project ID: " +
                                project_id + " doesn't exist")

        try:
            url = self.get_link(sample_URL, "sample/sequenceFiles",
                                targ_dict={
                                    "key":"sequencerSampleId",
                                    "value":sample_id
                                })

            response = self.session.get(url)

        except StopIteration:
            raise SampleError("The given sample ID: " +
                                sample_id + " doesn't exist")

        result = response.json()["resource"]["resources"]

        return result

    def send_projects(self, project):

        """
        post request to send a project to IRIDA via API
        the project being sent requires a name that is at least 5 characters long

        arguments:
            project -- a Project object to be sent.

        returns a dictionary containing the result of post request. when post is successful the dictionary it returns will contain the same name and projectDescription that was originally sent as well as additional keys like createdDate and identifier.
        when post fails then an error will be raised so return statement is not even reached.
        """

        json_res = None
        if len(project.getName()) >= 5:
            url = self.get_link(self.base_URL, "projects")
            json_obj = json.dumps(project.getDict())
            headers = {
                "headers": {
                    "Content-Type":"application/json"
                }
            }

            response = self.session.post(url,json_obj, **headers)

            if response.status_code == httplib.CREATED:#201
                json_res = json.loads(response.text)
            else:
                raise ProjectError("Error: " +
                                str(response.status_code) + " " + response.text)

        else:
            raise ProjectError("Invalid project name: " +
                                project.getName() +
                                ". A project requires a name that must be 5 or more characters.")

        return json_res

    def send_samples(self, project, samples_list):

        """
        post request to send sample(s) to the given project

        arguments:
            project -- a Project object used to get project ID
            samples_list -- list containing Sample object(s) to send

        returns a dictionary containing the result of post request.
        """

        json_res = None
        project_id = project.getID()
        try:
            proj_URL = self.get_link(base_URL, "projects")
            url = self.get_link(proj_URL, "project/samples",
                                targ_dict={
                                    "key":"identifier",
                                    "value":project_id
                                })

            response = self.session.get(url)

        except StopIteration:
            raise ProjectError("The given project ID: " +
                                project_id + " doesn't exist")

        headers = {
            "headers": {
                "Content-Type":"application/json"
            }
        }

        for sample in samples_list:
            json_obj = json.dumps(sample.getDict())
            response = self.session.post(url, json_obj, **headers)

            if response.status_code == httplib.CREATED:#201
                json_res = json.loads(response.text)
            else:
                raise SampleError("Error: " +
                                str(response.status_code) + " " + response.text)

        return json_res


if __name__=="__main__":
    base_URL="http://localhost:8080/api"
    username="admin"
    password="password1"

    path_to_module=path.dirname(__file__)
    if len(path_to_module)==0:
        path_to_module="."

    conf_Parser=RawConfigParser()
    conf_Parser.read(path_to_module+"/../config.conf")
    client_id=conf_Parser.get("apiCalls","client_id")
    client_secret=conf_Parser.get("apiCalls","client_secret")

    api=ApiCalls(client_id, client_secret, base_URL, username, password )

    proj_list=api.get_projects()
    print "#Project count:", len(proj_list)

    p=Project("projectX",projectDescription="orange")
    print api.send_projects(p)

    proj_list=api.get_projects()
    print "#Project count:", len(proj_list)

    print "#"*20


    proj_targ=proj_list[0]
    sList=api.get_samples(proj_targ)
    print "#Sample count:", len(sList)

    s=Sample({"sequencerSampleId":"09-9999","sampleName":"09-9999"})
    print api.send_samples(proj_targ, [s])#raises error on second run because ID won't be unique anymore for same proj_targ

    sList=api.get_samples(proj_targ)
    print "#Sample count:", len(sList)


    print "#"*20

    proj_targ=proj_list[3]
    sList=api.get_samples(proj_targ)
    seqFiles=api.get_sequence_files(proj_targ, sList[len(sList)-1])
    print seqFiles
