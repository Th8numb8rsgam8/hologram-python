# from Hologram.HologramCloud import HologramCloud
# from Hologram.Network.Modem import EG25
import sys
import datetime
import time
import serial
from serial.tools import list_ports
import pdb

# modem = EG25.EG25()

# recv = modem.send_sms_message("+13175097462", "That's BOIIII!")


################################################################################

class ModemResult:
    Invalid = 'Invalid'
    NoMatch = 'NoMatch'
    Error = 'Error'
    Timeout = 'Timeout'
    OK = 'OK'


class SMS:

    def __init__(self, sender, timestamp, message):

        self.sender = sender
        self.timestamp = timestamp
        self.message = message

    def __repr__(self):

        temp_str = type(self).__name__ + ': '
        temp_str = temp_str + 'sender: ' + self.sender + ', '
        temp_str = temp_str + 'timestamp: ' + self.timestamp.strftime('%c') + ', '
        temp_str = temp_str + 'message: ' + self.message

        return temp_str


class SMSHandler:

	DEFAULT_SERIAL_READ_SIZE = 256
	DEFAULT_SERIAL_RETRIES = 0
	DEFAULT_SERIAL_TIMEOUT = 1
	DEFAULT_SEND_TIMEOUT = 10

	GSM = u"@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"

	EXT = {
		0x40: u'|',
		0x14: u'^',
		0x65: u'€',
		0x28: u'{',
		0x29: u'}',
		0x3C: u'[',
		0x3D: u'~',
		0x3E: u']',
		0x2F: u'\\',
	}


	def __init__(self):

		self._in_ext = False
		self._usb_ids = [('2c7c', '0125')]

		self._connect_serial_port()
		self._timeout = SMSHandler.DEFAULT_SERIAL_TIMEOUT


	def _connect_serial_port(self):

		for vid, pid in self._usb_ids:
			udevices = [x for x in list_ports.grep("{0}:{1}".format(vid, pid))]
			for idx, udevice in enumerate(udevices):
				try:
					self._serial_port = serial.Serial(
						udevice.device, 
						baudrate='9600',
						bytesize=8, 
						parity='N', 
						stopbits=1,
						timeout=1, 
						write_timeout=1)

					pdb.set_trace()
					if self._serial_port.is_open:
						print(f"{udevice.device} port opened for modem!!!")
						break
				except:
					print(f"{udevice.device} not responsive")
					if idx == len(udevices)-1 :
						sys.exit(1)


	def send_sms_message(self, phonenumber, message, timeout=DEFAULT_SEND_TIMEOUT):

		self._command("+CMGF", "1")

		ctrl_z = chr(26).encode('utf-8')
		ok, response = self._command(
			"+CMGS",
			f"\"{phonenumber}\"",
			prompt=b">",
			data=f"{message}\r",
			commit_cmd=ctrl_z,
			timeout=timeout
		)

		self._command("+CMGF", "0")
		return ok == ModemResult.OK


	def popReceivedSMS(self):

		result, response = self._command("+CMGL")
		if result != ModemResult.OK: return None
		oldest = None
		oldest_index = None
		for i in range(0, len(response), 2):
			current, current_index = self._parsePDU(response[i], response[i+1])
			if current is None: continue
			if oldest is None or current.timestamp < oldest.timestamp:
				oldest = current
				oldest_index = current_index
		if oldest_index is not None:
			self._command("+CMGD", str(oldest_index))
		return oldest


	def _command(self, 
		cmd='', value=None, 
		expected=None, timeout=None,
		retries=DEFAULT_SERIAL_RETRIES, 
		seteq=False, read=False,
		prompt=None, data=None, 
		commit_cmd=None):

		try:
			return self._command_helper(
							cmd, value, 
							expected, timeout, 
							retries, seteq, 
							read, prompt, 
							data, commit_cmd)

		except serial.serialutil.SerialTimeoutException as e:
			self.result = ModemResult.Error
		return self._command_result()


	def _command_result(self):
		if self.result == ModemResult.OK and len(self.response) == 1:
			return self.result, self.response[0]
		else:
			return self.result, self.response


	def _readline_from_serial_port(self, timeout=None):
	    # Override set timeout with the given timeout if necessary
	    if timeout is not None:
	        self._serial_port.timeout = timeout
	    r = self._serial_port.readline()
	    r = r.decode('utf8')
	    # Revert back to original default timeout
	    if timeout is not None:
	        self._serial_port.timeout = self._timeout
	    return r


	def _parse_sender(self, pdu, offset):

		sms_deliver = int(pdu[offset],16)
		# options are SMS-SUBMIT, SMS-DELIVER or SMS-STATUS-REPORT
		# we are looking for a deliver, return none for other types
		if sms_deliver & 0x03 != 0: return None, offset
		offset += 1
		sender_len = int(pdu[offset:offset+2],16)
		offset += 2
		sender_number_type = int(pdu[offset:offset+2],16)
		offset += 2
		sender_read = sender_len
		if sender_read & 1 != 0: sender_read += 1
		sender_raw = pdu[offset:offset+sender_read]

		sender = None
		if sender_number_type & 0x50 == 0x50:
			#GSM-7
			sender = self._convert7to8bit(sender_raw, sender_len*4/7)
		else:
			sender = ''.join([ sender_raw[x:x+2][::-1] for x in range(0, len(sender_raw), 2) ])
			if sender_read & 1 != 0: sender = sender[:-1]
		offset += sender_read

		return sender, offset


	def _convert7to8bit(self, pdu, msg_len):
		last = 0
		current = 0
		i = 0
		msg = u''
		for count in range(msg_len):
			offset = count % 8
			last = current
			if offset < 7:
				current = int(pdu[i*2:i*2+2],16)
				i += 1
			c = (last >> (8-offset)) | (current << offset)
			msg += self._gsm7tochr(c & 0x7F)
		return msg


	def _gsm7tochr(self, c):
		if self._in_ext:
			self._in_ext = False
			if c in SMSHandler.EXT.keys():
				return SMSHandler.EXT[c]
		elif c == 0x1B:
			self._in_ext = True
			return u''
		elif c < len(SMSHandler.GSM):
			return SMSHandler.GSM[c]
		return u' '


	def _parse_timestamp(self, pdu, offset):

		timestamp_raw = pdu[offset:offset+14]
		timestamp = ''.join(
			[ timestamp_raw[x:x+2][::-1] for x in range(0, len(timestamp_raw), 2) ]
		)

		formatted_dt_str = self._format_datetime(timestamp[:-2])

		tz_byte = int(timestamp[-2:], 16)
		tz_bcd = ((tz_byte & 0x70) >> 4) * 10 + (tz_byte & 0x0F)

		delta = datetime.timedelta(minutes=15 * tz_bcd)

		# adjust to UTC from Service Center timestamp
		if (tz_byte & 0x80) == 0x80:
			formatted_dt_str += delta
		else:
			formatted_dt_str -= delta

		return formatted_dt_str, offset


	def _format_datetime(self, date_str):
		return datetime.datetime.strptime(date_str, '%y%m%d%H%M%S')


	# EFFECTS: Parses the rest of of the sms pdu (message).
	def _parse_message(self, pdu, offset):

		offset += 14
		msg_len = int(pdu[offset:offset + 2], 16)
		offset += 2
		return self._convert7to8bit(pdu[offset:], msg_len), offset


	# ['+CMGL: 2,1,,26', '0791447779071413040C9144977304250500007160421062944008D4F29C0E8AC966'])
	def _parsePDU(self, header, pdu):

		try:
			if not header.startswith("+CMGL: "):
				return None, None

			index, stat, alpha, length = header[7:].split(',')

			# parse PDU
			smsc_len = int(pdu[0:2], 16)

			# smsc_number_type = int(pdu[2:4],16)
			# if smsc_number_type != 0x81 and smsc_number_type != 0x91: return (-2, hex(smsc_number_type))
			offset = smsc_len*2 + 3

			sender, offset = self._parse_sender(pdu, offset)

			if pdu[offset:offset+4] != '0000':
				return None, None

			offset += 4

			timestamp, offset = self._parse_timestamp(pdu, offset)
			message, offset = self._parse_message(pdu, offset)

			return SMS(sender, timestamp, message), index

		except ValueError as e:
			self.logger.error(repr(e))

		return None, None


	def _command_helper(
			self, cmd='', value=None, 
			expected=None, timeout=None, 
			retries=DEFAULT_SERIAL_RETRIES, seteq=False, 
			read=False, prompt=None, 
			data=None, commit_cmd=None):

		self.result = ModemResult.Timeout

		if cmd.endswith('?'):
			read = True
			if cmd.endswith('=?'):
				cmd = cmd[:-2]
				seteq = True
			else:
				cmd = cmd[:-1]

		for i in range(retries+1):
			if value is None:
				self._modemwrite(cmd, start=True, at=True, read=read, end=True, seteq=seteq)
			elif read:
				self.result = ModemResult.Invalid
				return self._command_result()
			else:
				self._modemwrite(cmd, start=True, at=True, seteq=True)
				self._modemwrite(value, end=True)

			if not (prompt is None or data is None):

				p = self._read_from_serial_port(timeout, len(prompt) + 3)

				if prompt in p:
					time.sleep(1)
					self._write_to_serial_port_and_flush(data)
					if commit_cmd:
						self._write_to_serial_port_and_flush(commit_cmd)

			self.result = self._process_response(cmd, timeout)
			if self.result == ModemResult.OK:
				if expected is not None:
					self.result = ModemResult.NoMatch
					for s in self.response:
						if s.startswith(expected):
							self.result = ModemResult.OK
							break
				break
		return self._command_result()


	def _modemwrite(
		self, cmd, 
		start=False, at=False, seteq=False, 
		read=False, end=False):

		# Skip debugs for modem write commands if hidden mode is enabled.
		if at:
			self._write_to_serial_port_and_flush('AT')
		self._write_to_serial_port_and_flush(cmd)
		if seteq:
			self._write_to_serial_port_and_flush('=')
		if read:
			self._write_to_serial_port_and_flush('?')
		if end:
			self._write_to_serial_port_and_flush('\r\n')


	def _write_to_serial_port_and_flush(self, message):
		if isinstance(message, str):
			self._serial_port.write(message.encode())
		else:
			self._serial_port.write(message)
		self._serial_port.flush()


	# EFFECTS: This actually reads bytes from the serial port instance.
	def _read_from_serial_port(self, timeout=None, size=DEFAULT_SERIAL_READ_SIZE):
		if timeout is not None:
			self._serial_port.timeout = timeout
		r = self._serial_port.read(size)
		# Revert back to original default timeout
		if timeout is not None:
			self._serial_port.timeout = self._timeout
		return r


	def _process_response(self, cmd, timeout=None):
		self.response = []
		while(True):
			response = self._readline_from_serial_port(timeout)
			if len(response) == 0:
				return ModemResult.Timeout

			response = response.rstrip('\r\n')

			if len(response) == 0:
				continue

			if response == 'ERROR':
				return ModemResult.Error

			if response.startswith('+CME ERROR:') or response.startswith('+CMS ERROR:'):
				self.response.append(response)
				return ModemResult.Error

			if response == 'OK':
				return ModemResult.OK

			if response == 'SEND OK':
				return ModemResult.OK

			if response.startswith('+'):
				if response.lower().startswith(cmd.lower() + ': '):
					self.response.append(response)
				# else:
				#     self.handleURC(response)
			elif response.startswith('AT'+cmd):
				continue #echo log???
			else:
				self.response.append(response)

		return ModemResult.Timeout

	# def enableSMS(self):
	#     self.checkURC()
	#     ok, r = self.read("+CPMS")
	#     if ok == ModemResult.OK:
	#         try:
	#             numsms = int(r.lstrip('+CPMS: ').split(',')[1])
	#             for i in range(numsms):
	#                 self.event.broadcast('sms.received')
	#         except (IndexError, ValueError) as e:
	#             self.logger.error(repr(e))

if __name__ == "__main__":

	sms_handler = SMSHandler()

	recv = sms_handler.send_sms_message("+13175097462", "That's BOIIII!")
	# pdb.set_trace()
	while True:
		message = sms_handler.popReceivedSMS()
		time.sleep(1)
		if message is not None:
			print(message)
			break
