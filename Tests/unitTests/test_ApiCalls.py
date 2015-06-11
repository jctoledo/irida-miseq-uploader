import unittest
import json
import httplib
from sys import path, argv
path.append("../../")
from urllib2 import URLError, urlopen, HTTPError

from mock import patch, MagicMock
from rauth import OAuth2Service
from rauth.session import OAuth2Session
from requests.exceptions import HTTPError as request_HTTPError
from requests.models import Response

import API.apiCalls

class Foo(object):
	"""
	Class used to attach attributes
	"""
	def __init__(self):
		pass

class TestApiCalls(unittest.TestCase):

	def setUp(self):

		print "\nStarting ", self._testMethodName

	@patch("API.apiCalls.urlopen")
	@patch("API.apiCalls.ApiCalls.create_session")
	def test_validate_URL_existence_url_ok(self, mock_cs, mock_url):

		url_ok = Foo()
		setattr(url_ok,"code", httplib.OK)

		mock_url.side_effect = [url_ok]
		mock_cs.side_effect = [None]

		api = API.apiCalls.ApiCalls("","","","","")
		validate_URL = api.validate_URL_existence

		url = "http://google.com"
		valid = True

		is_valid = validate_URL(url)
		self.assertEqual(is_valid, valid)
		API.apiCalls.urlopen.assert_called_with(url, timeout=api.max_wait_time)

	@patch("API.apiCalls.urlopen")
	@patch("API.apiCalls.ApiCalls.create_session")
	def test_validate_URL_existence_url_raise_err(self, mock_cs, mock_url):

		url_raise_err = Foo()
		err_msg = "Unauthorized"
		setattr(url_raise_err, "code", httplib.UNAUTHORIZED)
		setattr(url_raise_err, "msg", err_msg)

		mock_url.side_effect = [url_raise_err]

		mock_cs.side_effect = [None]

		api=API.apiCalls.ApiCalls(
			client_id="",
			client_secret="",
			base_URL="",
			username="",
			password=""
		)

		validate_URL = api.validate_URL_existence

		url = "http://localhost:8080/api/"
		valid = True

		with self.assertRaises(Exception) as err:
			is_valid = validate_URL(url)

		self.assertTrue(err_msg in str(err.exception))
		API.apiCalls.urlopen.assert_called_with(url, timeout=api.max_wait_time)

	@patch("API.apiCalls.urlopen")
	@patch("API.apiCalls.ApiCalls.create_session")
	def test_validate_URL_existence_url_not_found(self, mock_cs, mock_url):

		url_not_found = Foo()
		setattr(url_not_found, "code", httplib.NOT_FOUND)

		mock_url.side_effect = [url_not_found]
		mock_cs.side_effect = [None]

		api = API.apiCalls.ApiCalls("","","","","")
		validate_URL = api.validate_URL_existence

		url = "notAWebSite"
		valid = False

		is_valid = validate_URL(url)
		self.assertEqual(is_valid, valid)
		API.apiCalls.urlopen.assert_called_with(url, timeout=api.max_wait_time)

	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	@patch("API.apiCalls.ApiCalls.get_access_token")
	@patch("API.apiCalls.ApiCalls.get_oauth_service")
	@patch("API.apiCalls.validate_URL_Form")
	def test_create_session_valid_base_url_no_slash(
								self, mock_validate_url_form,
								mock_get_oauth_service, mock_get_access_token,
								mock_validate_url_existence):

		oauth_service=Foo()
		access_token=Foo()
		setattr(oauth_service, "get_session", lambda x: "newSession1")

		mock_validate_url_form.side_effect = [True]
		mock_get_oauth_service.side_effect = [oauth_service]
		mock_get_access_token.side_effect = [access_token]
		mock_validate_url_existence.side_effect=[True]

		base_URL1="http://localhost:8080"
		api1=API.apiCalls.ApiCalls(
		  client_id="",
		  client_secret="",
		  base_URL=base_URL1,
		  username="",
		  password=""
		)

		self.assertEqual(api1.session, oauth_service.get_session(access_token))
		mock_validate_url_existence.assert_called_with(base_URL1 + "/", use_session=True)

	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	@patch("API.apiCalls.ApiCalls.get_access_token")
	@patch("API.apiCalls.ApiCalls.get_oauth_service")
	@patch("API.apiCalls.validate_URL_Form")
	def test_create_session_valid_base_url_slash(
								self, mock_validate_url_form,
								mock_get_oauth_service, mock_get_access_token,
								mock_validate_url_existence):

		oauth_service=Foo()
		access_token=Foo()
		setattr(oauth_service, "get_session", lambda x: "newSession2")

		mock_validate_url_form.side_effect = [True]
		mock_get_oauth_service.side_effect = [oauth_service]
		mock_get_access_token.side_effect = [access_token]
		mock_validate_url_existence.side_effect=[True]

		base_URL2="http://localhost:8080/"
		api2=API.apiCalls.ApiCalls(
		  client_id="",
		  client_secret="",
		  base_URL=base_URL2,
		  username="",
		  password=""
		)

		self.assertEqual(api2.session, oauth_service.get_session(access_token))
		mock_validate_url_existence.assert_called_with(base_URL2, use_session=True)

	@patch("API.apiCalls.validate_URL_Form")
	def test_create_session_invalid_form(self, mock_validate_url_form):

		mock_validate_url_form.side_effect = [False]

		base_URL = "invalidForm.com/"
		with self.assertRaises(URLError) as err:
			api=API.apiCalls.ApiCalls(
			  client_id="",
			  client_secret="",
			  base_URL=base_URL,
			  username="",
			  password=""
			)

		self.assertTrue("not a valid URL" in str(err.exception))
		mock_validate_url_form.assert_called_with(base_URL)

	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	@patch("API.apiCalls.ApiCalls.get_access_token")
	@patch("API.apiCalls.ApiCalls.get_oauth_service")
	@patch("API.apiCalls.validate_URL_Form")
	def test_create_session_invalid_session(self, mock_validate_url_form,
											mock_get_oauth_service,
											mock_get_access_token,
											mock_validate_url_existence):

		oauth_service = Foo()
		access_token = Foo()
		setattr(oauth_service, "get_session", lambda x: "newSession")

		mock_validate_url_form.side_effect = [True]
		mock_get_oauth_service.side_effect = [oauth_service]
		mock_get_access_token.side_effect = [access_token]
		mock_validate_url_existence.side_effect = [False]

		with self.assertRaises(Exception) as err:
			api=API.apiCalls.ApiCalls(
			  client_id="",
			  client_secret="",
			  base_URL="",
			  username="",
			  password=""
			)

		expectedErrMsg = "Cannot create session. Verify your credentials are correct."
		self.assertTrue(expectedErrMsg in str(err.exception))
		mock_validate_url_form.assert_called_with("/")

	@patch("API.apiCalls.ApiCalls.create_session")
	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	def test_get_link_valid(self,
							mock_validate_url_existence,
	          				mock_cs):

		mock_validate_url_existence.side_effect = [True]
		mock_cs.side_effect = [None]

		api=API.apiCalls.ApiCalls(
			client_id="",
			client_secret="",
			base_URL="",
			username="",
			password=""
		)

		targ_URL = "http://localhost:8080/api/"
		targ_key = "project"
		targ_link = "http://localhost:8080/api/project"

		session = Foo()
		json_obj = {
			"resource" : {
				"links" : [
					{
						"rel" : targ_key,
						"href" : targ_link
					}
				]
			}
		}

		#session.get will return json_response
		#json_response has a callable json attribute that returns json_obj
		json_response = Foo()
		setattr(json_response,"json", lambda: json_obj)

		session_get = MagicMock(side_effect=[json_response])
		setattr(session,"get", session_get)

		api.session = session
		link=api.get_link(targ_URL, targ_key)

		api.session.get.assert_called_with(targ_URL)
		self.assertEqual(link, targ_link)

	@patch("API.apiCalls.ApiCalls.create_session")
	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	def test_get_link_valid_targ_dict(self,
							mock_validate_url_existence,
	          				mock_cs):

		mock_validate_url_existence.side_effect = [True]
		mock_cs.side_effect = [None]

		api=API.apiCalls.ApiCalls(
			client_id="",
			client_secret="",
			base_URL="",
			username="",
			password=""
		)

		targ_URL = "http://localhost:8080/api/"
		targ_key = "project"
		targ_link = "http://localhost:8080/api/project"

		session = Foo()
		json_obj = {
			"resource" : {
				"resources" : [{
					"identifier" : "1",
					"links" : [
						{
							"rel" : targ_key,
							"href" : targ_link
						}
					]
				}]

			}
		}

		#session.get will return json_response
		#json_response has a callable json attribute that returns json_obj
		json_response = Foo()
		setattr(json_response,"json", lambda: json_obj)

		session_get = MagicMock(side_effect=[json_response])
		setattr(session,"get", session_get)

		api.session = session
		t_dict={"key":"identifier","value":"1"}
		link=api.get_link(targ_URL, targ_key, targ_dict=t_dict)

		api.session.get.assert_called_with(targ_URL)
		self.assertEqual(link, targ_link)



	@patch("API.apiCalls.ApiCalls.create_session")
	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	def test_get_link_invalid_url_not_found(self,
											mock_validate_url_existence,
	          								mock_cs):

		mock_validate_url_existence.side_effect = [False]
		mock_cs.side_effect = [None]

		api=API.apiCalls.ApiCalls(
			client_id="",
			client_secret="",
			base_URL="",
			username="",
			password=""
		)

		targ_URL = "http://localhost:8080/api/"
		targ_key = "project"

		with self.assertRaises(request_HTTPError) as err:
			api.get_link(targ_URL, targ_key)

		self.assertTrue("not a valid URL" in str(err.exception))
		mock_validate_url_existence.assert_called_with(targ_URL,
														use_session=True)

	@patch("API.apiCalls.ApiCalls.create_session")
	@patch("API.apiCalls.ApiCalls.validate_URL_existence")
	def test_get_link_invalid_key_not_found(self,
											mock_validate_url_existence,
	          								mock_cs):

		mock_validate_url_existence.side_effect = [True]
		mock_cs.side_effect = [None]

		api=API.apiCalls.ApiCalls(
			client_id="",
			client_secret="",
			base_URL="",
			username="",
			password=""
		)

		targ_URL = "http://localhost:8080/api/"
		targ_key = "project"
		targ_link = "http://localhost:8080/api/project"
		invalid_key = "notProject"

		session = Foo()
		json_obj = {
			"resource" : {
				"links" : [
					{
						"rel" : invalid_key,
						"href" : targ_link
					}
				]
			}
		}

		#session.get will return json_response
		#json_response has a callable json attribute that returns json_obj
		json_response = Foo()
		setattr(json_response,"json", lambda: json_obj)

		session_get = MagicMock(side_effect=[json_response])
		setattr(session,"get", session_get)

		api.session = session
		with self.assertRaises(KeyError) as err:
			api.get_link(targ_URL, targ_key)

		self.assertTrue(targ_key + " not found in links" in str(err.exception))
		self.assertTrue("Available links: " + invalid_key in str(err.exception))
		api.session.get.assert_called_with(targ_URL)

	###Below still needs to be updated
	def test_getProjects(self):

		createSession=API.apiCalls.createSession
		getProjects=API.apiCalls.getProjects

		baseURL="http://localhost:8080/api/"
		username="admin"
		password="password1"

		API.apiCalls.urlopen=self.setUpMock(urlopen)

		session=createSession(baseURL, username, password)

		projectLinkResponse=OAuth2Session('123','456', access_token='321')
		projectsListResponse=OAuth2Session('123','456', access_token='321')

		projectLinkJson={u'resource':{u'links':[{'rel':u'projects',u'href':u'http://localhost:8080/api/projects'}]}}
		projectsListJson={u'resource':{u'resources': [{u'projectDescription': None, u'identifier': u'1', u'name': u'Project1',u'createdDate':1432050859000},{u'projectDescription': None, u'identifier': u'2', u'name':u'Project 3', u'createdDate':1432050853000}]}, u'links':[		{'rel':u'projects',u'href':u'http://localhost:8080/api/projects'}]}

		setattr(projectLinkResponse,"json", lambda : projectLinkJson)#lambda returns function - since json attribute will be a callable function (i.e mockResponse.json() instead of mockResponse.json)
		setattr(projectLinkResponse,"status_code", httplib.OK)
		setattr(projectsListResponse,"json", lambda : projectsListJson)
		setattr(projectsListResponse,"status_code", httplib.OK)

		funcHolder=API.apiCalls.OAuth2Session.get
		API.apiCalls.OAuth2Session.get=self.setUpMock(OAuth2Session.get, [projectLinkResponse, projectsListResponse] )

		projList=getProjects(session, baseURL)

		if self.mocking==True:#only test if mocking enabled since irida server actually returns number of projects (>100)
			API.apiCalls.OAuth2Session.get.assert_called_with(projectLinkJson["resource"]["links"][0]["href"])
			self.assertEqual(len(projList), 2)
			projNames= [ proj["name"] for proj in projList ]
			expectedRes= [ proj["name"] for proj in projectsListJson["resource"]["resources"] ]
			self.assertEqual(projNames, expectedRes)


		expectedKeys=set( ("name","projectDescription") )
		for proj in projList:
			self.assertTrue( all([key in proj.keys() for key in expectedKeys]))

		API.apiCalls.OAuth2Session.get=funcHolder


	def test_sendProjects_valid(self):
		createSession=API.apiCalls.createSession
		sendProjects=API.apiCalls.sendProjects

		baseURL="http://localhost:8080/api/"
		username="admin"
		password="password1"
		headers = {'headers': {'Content-Type':'application/json'}}

		mockResponse=OAuth2Session('123','456', access_token='321')
		expectedDict={
			"resource":
			{
				"projectDescription" : "This is a test project",
				"name" : "testProject",
				"identifier" : "123",
				"createdDate" : 1433173545000
			}
		}

		jsonResponse=json.dumps(expectedDict)
		setattr(mockResponse,"text", jsonResponse)
		setattr(mockResponse,"status_code", httplib.CREATED)

		API.apiCalls.urlopen=self.setUpMock(urlopen)

		funcHolder=API.apiCalls.OAuth2Session.post
		API.apiCalls.OAuth2Session.post=self.setUpMock(API.apiCalls.OAuth2Session.post, [mockResponse] )

		session=createSession(baseURL, username, password)

		projToSend= {"name":"testProject", "projectDescription": "This is a test project"}
		res=sendProjects(session , baseURL, projToSend)

		if self.mocking==True:
			API.apiCalls.OAuth2Session.post.assert_called_with(baseURL+"projects", json.dumps(projToSend), **headers  )

		#check that names and project descriptions are the same
		for key in projToSend.keys():
			self.assertEqual(res["resource"][key], expectedDict["resource"][key])

		API.apiCalls.OAuth2Session.post=funcHolder


	def test_sendProjects_invalid(self):
		createSession=API.apiCalls.createSession
		sendProjects=API.apiCalls.sendProjects

		baseURL="http://localhost:8080/api/"
		username="admin"
		password="password1"
		headers = {'headers': {'Content-Type':'application/json'}}

		mockResponse=OAuth2Session('123','456', access_token='321')
		jsonResponse=json.dumps(
		{
			"resource":
			{
				"projectDescription" : "This is a test project",
				"name" : "testProject",
				"identifier" : "123",
				"createdDate" : 1433173545000
			}
		})
		setattr(mockResponse,"text", jsonResponse)
		setattr(mockResponse,"status_code", httplib.CREATED)

		API.apiCalls.urlopen=self.setUpMock(urlopen)

		funcHolder=API.apiCalls.OAuth2Session.post
		API.apiCalls.OAuth2Session.post=self.setUpMock(API.apiCalls.OAuth2Session.post, [mockResponse] )

		session=createSession(baseURL, username, password)

		projToSend= {"projectDescription": "This project has no name"}

		with self.assertRaises(API.apiCalls.ProjectError) as context:
			res=sendProjects(session , baseURL, projToSend)

		self.assertTrue("Missing project name" in str(context.exception))

		if self.mocking==True:
			assert not API.apiCalls.OAuth2Session.post.called

		API.apiCalls.OAuth2Session.post=funcHolder


api_TestSuite= unittest.TestSuite()

api_TestSuite.addTest(TestApiCalls("test_validate_URL_existence_url_ok"))
api_TestSuite.addTest(TestApiCalls("test_validate_URL_existence_url_raise_err"))
api_TestSuite.addTest(TestApiCalls("test_validate_URL_existence_url_not_found"))
api_TestSuite.addTest(TestApiCalls("test_create_session_valid_base_url_no_slash"))
api_TestSuite.addTest(TestApiCalls("test_create_session_valid_base_url_slash"))
api_TestSuite.addTest( TestApiCalls("test_create_session_invalid_form"))
api_TestSuite.addTest( TestApiCalls("test_create_session_invalid_session"))
api_TestSuite.addTest( TestApiCalls("test_get_link_valid"))
api_TestSuite.addTest( TestApiCalls("test_get_link_valid_targ_dict"))
api_TestSuite.addTest( TestApiCalls("test_get_link_invalid_url_not_found"))
api_TestSuite.addTest( TestApiCalls("test_get_link_invalid_key_not_found"))
#api_TestSuite.addTest( TestApiCalls("test_get_link_invalid_targ_dict_value"))
#api_TestSuite.addTest( TestApiCalls("test_getProjects") )
#api_TestSuite.addTest( TestApiCalls("test_sendProjects_valid") )
#api_TestSuite.addTest( TestApiCalls("test_sendProjects_invalid") )

if __name__=="__main__":
	suiteList=[]

	suiteList.append(api_TestSuite)
	fullSuite = unittest.TestSuite(suiteList)

	runner = unittest.TextTestRunner()
	runner.run(fullSuite)
