import sys, socket, errno, struct, logging
from .cnsparser import argparser
from .config import config
from .utils import socket_uri
from . import cnsexitcode, cnscom, cnsexc

###

L = logging.getLogger("cnsapp")

###

class console_app(object):
	'''
Console application (base for custom implementations)
	'''

	def __init__(self):
		self.argparser = argparser()

		if (len(sys.argv) < 2):
			# Default command
			argv = ['console']
		else:
			argv = None

		self.argparser.parse(argv)

		# Read config
		from .config import read_config
		read_config(self.argparser.args.config)

		# Configure logging
		logging.basicConfig(level=logging.DEBUG) #TODO: Improve this ...

		# Prepare server connection factory
		self.cnsconuri = socket_uri(config.get('console','serveruri'))
		self.ctlconsock = None


	def run(self):
		exitcode = self.argparser.execute(self)
		sys.exit(exitcode if not None else cnsexitcode.OK)


	def connect(self):
		if self.ctlconsock is None: 
			try:
				self.ctlconsock = self.cnsconuri.create_socket_connect()
			except socket.error, e:
				if e.errno == errno.ECONNREFUSED: return None
				if e.errno == errno.ENOENT and self.cnsconuri.protocol == 'unix': return None
				raise

		return self.ctlconsock


	def svrcall(self, callid, params="", auto_connect=False):
		if auto_connect:
			if self.ctlconsock is None:
				s = self.connect()
				if s is None:
					raise cnsexc.server_not_responing_error("Server is not responding - maybe it isn't running.")

		else:
			assert self.ctlconsock is not None

		paramlen = len(params)
		if paramlen >= 256*256:
			raise RuntimeError("Transmitted parameters are too long.")

		self.ctlconsock.send(struct.pack(cnscom.call_struct_fmt, cnscom.call_magic, callid, paramlen)+params)
		
		import time
		x = time.time()
		resp = ""
		while len(resp) < 4:
			resp += self.ctlconsock.recv(4 - len(resp))
			if len(resp) == 0:
				if time.time() - x > 2:
					print "Looping detected"
					time.sleep(5)

		magic, retype, paramlen = struct.unpack(cnscom.resp_struct_fmt, resp)
		assert magic == cnscom.resp_magic
		params = self.ctlconsock.recv(paramlen)
		
		if retype == cnscom.resp_ret:
			# Remote server call returned normally
			return params
		
		elif retype == cnscom.resp_exc:
			# Remove server call returned exception
			raise RuntimeError(params)
		
		else:
			raise RuntimeError("Unknown server response: {0}".format(retype))

