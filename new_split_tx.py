import numpy
import gras
import time
from PMC import *
from math import pi
import Queue
import thread
from gnuradio import gr
from gnuradio import digital
from gnuradio import uhd
import grextras
import pdb

# cntrl commands
ACK_PKT_COL = 88
ACK_PKT_IDL = 89
ACK_PKT_SUC = 90
DATA_PKT = 91
PILOT_PKT = 92


BROADCAST_ADDR = 255

#block port definition
PHY_PORT=0
APP_PORT=1
CTRL_PORT=2


#Packet index definitions
PKT_INDEX_DEST = 0
PKT_INDEX_SRC = 1
PKT_INDEX_CNTRL_ID = 2     
PKT_INDEX_SEQ = 3

#ARQ Channel States
TX_CHANNEL_SENSE = 1
TX_DATA_SEND = 0



MAX_INPUT_QSIZE= 1000



class split_demo(gras.Block):
	"""
	four input port : port 0 for phy ; port 1 for application ; port 2 for ctrl ; 
	three output port : port 0 for phy , port 1 for application , port 2 for ctrl
	Stop and wait arq implementation with new message framework of gras motivated from pre-cog
	"""
	def __init__(self,dest_addr,source_addr,time_out,lower_H,higher_H,probe,threshold):
		gras.Block.__init__(self,name="simple_arq",
			in_sig = [numpy.uint8,numpy.uint8,numpy.uint8],
            out_sig = [numpy.uint8,numpy.uint8,numpy.uint8])
		self.input_config(0).reserve_items = 0
		self.input_config(1).reserve_items = 0
		self.input_config(2).reserve_items = 0
		
		self.output_config(1).reserve_items = 4096
		self.output_config(0).reserve_items = 4096
		self.threshold=threshold
		
		#self.device_addr="addr=10.32.19.164"
		self.dest_addr=dest_addr
		self.source_addr=source_addr
		self.time_out=time_out
		self.lower_H=lower_H
		self.higher_H=higher_H

		#state variable
		self.arq_expected_sequence_no=0
		self.pkt_retxed=0
		self.tx_time=0
		self.rx_time=0
		#self.tx_state=TX_DATA_SEND
		self.TX_CHANNEL_SENSE=False
		self.TX_DATA_SEND=False
		self.no_attempts=0
		self.failed_arq=0
		
		#measurement variable
		self.arq_sequence_err_cnt=0
		self.total_pkt_txed=0
		self.total_tx=0
		self.i=0
		self.pilot_rx_time=0
#		self.probe_level=1.23456789e11
		#Queue for app packets
		self.q=Queue.Queue()
		self.msg_from_app=0
		self.a=0

		#channel gain thresholds
		self.Hll=0
		

		#time intervals
		#self.interval_start=
		self.hop_interval=0.1
		#self.time_transmit_start=
		self.lead_limit=0.001
		self.post_guard=0.01
		#self.antenna_start=
	
		self.probe=probe
		print "inside split_demo"

	'''	self.uhd_usrp_sink = uhd.usrp_sink(
			device_addr=self.device_addr,
			stream_args=uhd.stream_args(
				cpu_format="fc32",
				channels=range(1),
			),
		)
	'''

		
	def param(self):
		print "Destination addr : ",self.dest_addr
		print "Source addr : ",self.source_addr
		print "TimeOut : ",self.time_out
		print "Max Attempts : ",self.max_attempts
	
	def work(self,ins,outs):
		#print "mac at work"
		#print self.probe.get("level")
		#Taking packet out of App port and puting them on queue
		self.channel_gain=self.probe.level()
		print "CHANNEL_GAIN:", self.channel_gain
		msg=self.pop_input_msg(APP_PORT)
		pkt_msg=msg()
		#if isinstance(pkt_msg, gras.PacketMsg): 
		if(pkt_msg):
			#print "msg from app ",  pkt_msg.buff.get().tostring()
			self.msg_from_app+=1
			self.q.put(pkt_msg.buff.get().tostring())

		#Taking packet msg out of CTRL port
		msg=self.pop_input_msg(CTRL_PORT)
		pkt_msg=msg()
		#if isinstance(pkt_msg, gras.PacketMsg): 
		if(pkt_msg):
			#print "Its time.."
			a=0 #control

		#Taking packet out of PHY port
		msg=self.pop_input_msg(PHY_PORT)
		pkt_msg=msg()	
		if(pkt_msg):
			msg_str=pkt_msg.buff.get().tostring()
			#print msg_str
			if(len(msg_str) >4):	
				print "RECEIVED SOMETHING"
				self.rx_time=time.time()
				print "AT :",self.rx_time
				self.channel_gain=self.probe.level()
				print "CHANNEL_GAIN FROM MAIN:", self.channel_gain
				
				#PILOT_PKT
				if(ord(msg_str[PKT_INDEX_CNTRL_ID])==PILOT_PKT):
						while(ord(msg_str[PKT_INDEX_SEQ])<100):
							self.channel_gain=self.probe.level()
							print "CHANNEL_GAIN AFTER SENSING:", self.channel_gain
							if(self.channel_gain<self.higher_H and self.channel_gain>self.lower_H):
								print "gain condition satisfied"
								print "PILOT NUMBER", ord(msg_str[PKT_INDEX_SEQ])
								self.pilot_rx_time=time.time()
								print "RECEIVED AT: ", self.pilot_rx_time
								self.TX_CHANNEL_SENSE=True
							break
						
				#ACK_PKT_SUC
				elif(ord(msg_str[PKT_INDEX_DEST])==self.source_addr and ord(msg_str[PKT_INDEX_CNTRL_ID])==ACK_PKT_SUC):
					print "SUCCESS ACK RCVD"
					if(ord(msg_str[PKT_INDEX_SEQ])==self.arq_expected_sequence_no):
						#print "pack tx successfully ",self.arq_expected_sequence_no
						print "ACK_PKT Rcvd"
						#self.nav=time.time()-self.tx_time
						self.arq_expected_sequence_no=(self.arq_expected_sequence_no+1)%255
						self.TX_CHANNEL_SENSE=False
						#self.send_pkt_phy(self.outgoing_msg,self.arq_expected_sequence_no,DATA_PKT)
						#self.tx_state=TX_DATA_SEND
			
					
				elif(ord(msg_str[PKT_INDEX_DEST])==self.source_addr and ord(msg_str[PKT_INDEX_CNTRL_ID])==ACK_PKT_COL):	
					print"packet collision"
					self.Hll=self.lower_H	
					print "Hll  ", self.Hll					
					self.lower_H=self.split_threshold(self.lower_H,self.higher_H)
					print "lower_H", self.lower_H
					self.TX_CHANNEL_SENSE=False
					#self.tx_state=TX_DATA_SEND

				elif(ord(msg_str[PKT_INDEX_DEST])==self.source_addr and ord(msg_str[PKT_INDEX_CNTRL_ID])==ACK_PKT_IDL):
					print"idle channel"
					self.higher_H=self.lower_H
					if(self.Hll!=0):
						self.lower_H=self.split_threshold(self.lower_H,self.higher_H)
						print "lower_H  ",self.lower_H
					else:
						self.lower_H=self.lower(self.lower_H)
					self.TX_CHANNEL_SENSE=False
			
				
			else:
				print "PKT IS SMALL"

		else:
			#print"Nothing found on phy port"
			a=0

		if(self.TX_CHANNEL_SENSE==True):
			if(time.time()>self.tx_time+0.05):
				self.TX_DATA_SEND=True
			else:
				self.TX_DATA_SEND=False
			self.TX_CHANNEL_SENSE=False

		if(self.TX_DATA_SEND==True):
			if not self.q.empty():
				self.outgoing_msg=self.q.get()
				self.send_pkt_phy(self.outgoing_msg,self.arq_expected_sequence_no,DATA_PKT)	
				self.tx_time=time.time()
				print"TRANSMIT TIME OF DATA : ",self.tx_time
				self.TX_DATA_SEND=False
		if(time.time()>self.pilot_rx_time+0.05):
			self.TX_CHANNEL_SENSE=True

	#post msg data to phy port- msg is string
	def send_pkt_phy(self,msg,pkt_cnt,protocol_id):
		#Framing MAC Info
		#self.usrp_sink.clear_command_time()
		#self.usrp_sink.set_command_time(uhd.time_spec_t(self.antenna_start))
		if(protocol_id==ACK_PKT_SUC):
			print "Transmitting ACK no. ",pkt_cnt
		else:
			print "Transmitting PKT no. ",pkt_cnt
		pkt_str=chr(self.dest_addr)+chr(self.source_addr)+chr(protocol_id)+chr(pkt_cnt)+msg
		#print msg

		#get a reference counted buffer to pass downstream
		buff = self.get_output_buffer(PHY_PORT)
		buff.offset = 0
		buff.length = len(pkt_str)
		buff.get()[:] = numpy.fromstring(pkt_str, numpy.uint8)
		self.post_output_msg(PHY_PORT,gras.PacketMsg(buff))
			
	#post msg data to app port - msg is string
	def send_pkt_app(self,msg):
		print "Recieved data packet."
 		#get a reference counted buffer to pass downstream
 		buff = self.get_output_buffer(APP_PORT)
		buff.offset = 0
		buff.length = len(msg)
		buff.get()[:] = numpy.fromstring(msg, numpy.uint8)
		self.post_output_msg(APP_PORT,gras.PacketMsg(buff))
	def split_threshold(self, lower_H, higher_H):
		self.new_H=(lower_H+higher_H)/2
		return (self.new_H)
	def lower(self, lower_H):
		new_H=lower_H*0.5
		return (self.new_H)
	
	def cs_busy(self):
		return self.probe.level()>self.threshold

