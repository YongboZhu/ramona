import datetime, socket, logging, pyev, time
from ..config import config
from ..sendmail import send_mail

#

L = logging.getLogger('notify')

#

class notificator(object):

	def __init__(self, svrapp):
		delivery = config.get('ramona:notify','delivery').strip()
		if delivery == '':
			self.delivery = None
		else:
			try:
				self.delivery = send_mail(delivery)
			except RuntimeError, e:
				L.error("{0}".format(e))
				self.delivery = None

			if self.delivery is not None:
				self.delivery.connection_test()
		
		# Example structure of this dict is:
		# {
		#   "foo@bar.com": [] # List of lines to be included in the mail
		# }
		self.dailystash = dict()
		if self.delivery is not None:
			svrapp.watchers.append(pyev.Periodic(self.__get_daily_time_offset(), 24*3600, svrapp.loop, self.__send_daily))


		#TODO: <sendmail> - see http://stackoverflow.com/questions/73781/sending-mail-via-sendmail-from-python
		#TODO: cmd:custom.sh
		
	def __get_daily_time_offset(self):
		sendtimestr = config.get("ramona:notify", "dailyat")
		
		# TODO: Enhance to better handle situation for the day when the timezone changes (switch from/to daylight saving time)
		sendtime = datetime.datetime.strptime(sendtimestr, "%H:%M").time()
		is_dst = time.daylight and time.localtime().tm_isdst > 0
		utc_offset = time.altzone if is_dst else time.timezone
		
		sendtimeseconds = sendtime.hour * 3600 + sendtime.minute * 60 + utc_offset
		
		if sendtimeseconds < 0:
			sendtimeseconds += 24*3600
		if sendtimeseconds >= 24*3600:
			sendtimeseconds -= 24*3600
		
		return sendtimeseconds
	
	
	def __send_daily(self, watcher, revents):
		# TODO: Call this on server shutdown not to lose any messages in the stash (or not???)
		watcher.offset = self.__get_daily_time_offset()
		watcher.reset()
		appname = config.get('general','appname')
		hostname = socket.gethostname()
		
		
		for recipient, ntftexts in self.dailystash.iteritems():
			# Use pop to get the items from the stash to ensure that items that are put on the stash
			# during sending are not sent twice (in the current email and in the next email)
			textssend = []
			while True:
				try:
					textssend.append(ntftexts.pop())
				except IndexError:
					break
				
			
			subj = '{0} / {1} - daily'.format(
					appname,
					hostname)
			sep = '\n'+'='*50+'\n'
			self._send_mail(subj, sep.join(textssend), [recipient])


	def publish(self, target, ntfbody, ntfsubj):
		if ntfsubj is None: ntfsubj = 'Ramona notification'
		targettime, _, recipientconf = target.partition(":")
		recipientconf = recipientconf.strip()
		if recipientconf != "":
			recipients = [recipientconf]
		else:
			if self.delivery is None:
				L.warning("No default delivery set for notifications.")
				return
			recipients = self.delivery.receiver

		
		if targettime == "now":
			self._send_mail(
				ntfsubj, 
				ntfbody,
				recipients
			)

		elif targettime == "daily":
			for recipient in recipients:
				if not self.dailystash.has_key(recipient):
					self.dailystash[recipient] = list()
				self.dailystash[recipient].append(ntfbody) #TODO: Add also ntfsubj (subject)
			
		else:
			L.warn("Target {} not implemented!".format(targettime))
			


	def _send_mail(self, subject, text, recipients):
		'''
		@param subject: Subject of the email message
		@param text: Text to be sent (it is prefixed with greeting and signature by this method)
		@param recipients: List of message recipients
		'''

		fqdn = socket.getfqdn()
		appname = config.get('general','appname')
		hostname = socket.gethostname()

		subject = '{0} / {1} / {2} (by Ramona)'.format(appname, hostname, subject)

		sysident = 'Application: {0}\n'.format(appname)
		if hostname != fqdn :
			sysident += 'Hostname: {0} / {1}'.format(hostname, fqdn)
		else:
			sysident += 'Hostname: {0}'.format(hostname)

		try:
			text = ''.join([
				'Hello,\n\nRamona produced following notification:\n', text,
				'\n\nSystem info:\n', sysident,
				'\n\nBest regards,\nYour Ramona\n\nhttp://ateska.github.com/ramona\n'
			])
			
			self.delivery.send(recipients, subject, text)

		except:
			L.exception('Exception during sending mail - ignoring')
