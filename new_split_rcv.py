import numpy
import gras
import time
from PMC import *
from math import pi
import Queue
import thread

# cntrl commands
ACK_PKT_COL = 88
ACK_PKT_IDL = 89
ACK_PKT_SUC = 90
DATA_PKT = 91
PILOT_PKT = 92
PILOT_PKT_INDEX = 0



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
RX_ACK_SEND = 2
RX_PILOT_SEND = 1
RX_CHANNEL_SENSE = 0


MAX_INPUT_QSIZE= 1000



class pilot_rcv(gras.Block):
	"""
	four input port : port 0 for phy ; port 1 for application ; port 2 for ctrl ; 
	three output port : port 0 for phy , port 1 for application , port 2 for ctrl
	Stop and wait arq implementation with new message framework of gras motivated from pre-cog
	"""
	def __init__(self,dest_addr,source_addr,probe,threshold):
		gras.Block.__init__(self,name="rcv_pilot",
			in_sig = [numpy.uint8,numpy.uint8,numpy.uint8],
            out_sig = [numpy.uint8,numpy.uint8,numpy.uint8])
		self.input_config(0).reserve_items = 0
		self.input_config(1).reserve_items = 0
		self.input_config(2).reserve_items = 0
		
		self.output_config(1).reserve_items = 4096
		self.output_config(0).reserve_items = 4096
		

		self.dest_addr=dest_addr
		self.source_addr=source_addr
		self.threshold=threshold
		#state variable
		self.arq_expected_sequence_no=0
		self.pkt_retxed=0
		self.tx_time=0
		self.rx_time=0
		self.pilot_pkt_index=0
		#self.arq_state=ARQ_CHANNEL_IDLE
		self.RX_PILOT_SEND=True
		self.RX_CHANNEL_SENSE=False
		self.RX_ACK_SEND=False
		self.no_attempts=0
		self.pilot_tx_time=0
		self.failed_arq=0
		self.success=False
		self.collision=False
		#measurement variable
		self.arq_sequence_err_cnt=0
		self.total_pkt_txed=0
		self.total_tx=0
		self.i=1
		#Queue for app packets
		self.q=Queue.Queue()
		self.a=0
		self.pilot_txd=0
		self.probe=probe
	
	def param(self):
		print "Destination addr : ",self.dest_addr
		print "Source addr : ",self.source_addr

	def work(self,ins,outs):
		#print "mac at work"
		msg=self.pop_input_msg(APP_PORT)
		pkt_msg=msg()
		#if isinstance(pkt_msg, gras.PacketMsg): 
		if(pkt_msg):
			#print "msg from app ",  pkt_msg.buff.get().tostring()
			self.q.put(pkt_msg.buff.get().tostring())
		
		if(self.RX_PILOT_SEND==True):
			if not self.q.empty():
				self.outgoing_msg=self.q.get()
				self.send_pkt_phy(self.outgoing_msg,self.pilot_pkt_index,self.dest_addr,PILOT_PKT)
				self.pilot_tx_time=time.time()
				print "PILOT TX TIME : ", self.pilot_tx_time
				self.RX_PILOT_SEND=False
				self.RX_CHANNEL_SENSE=True	

		if(self.RX_CHANNEL_SENSE==True):
			self.channel_gain=self.probe.level()
			print "CHANNEL_GAIN AFTER SENSING:", self.channel_gain
			if(time.time<self.pilot_tx_time+0.01):
				self.RX_PILOT_SEND=True
			else:
				self.pilot_pkt_index=(self.pilot_pkt_index+1)%255
			self.RX_CHANNEL_SENSE=False								
		#Taking packet msg out of CTRL port
		msg=self.pop_input_msg(CTRL_PORT)
		pkt_msg=msg()
		if(pkt_msg):
			
			a=0 #control			

		#Taking packet msg out of PHY port
		msg=self.pop_input_msg(PHY_PORT)
		pkt_msg=msg()
		if(pkt_msg):
			msg_str=pkt_msg.buff.get().tostring()
			#print"THE MESSAGE IS", msg_str
			if(len(msg_str) >4):
				print "RECEIVED SOMETHING"
				print ord(msg_str[PKT_INDEX_DEST])
				if(ord(msg_str[PKT_INDEX_DEST])==self.source_addr):
					if(ord(msg_str[PKT_INDEX_CNTRL_ID])==DATA_PKT):
						self.rx_time=time.time()
						#send ack
						#time.sleep(0.015)
						self.RX_ACK_SEND=True
						self.success=True
					
				if(self.probe.level()>self.threshold):
					#print "PROBE LEVEL : ",self.probe.level
					#time.sleep(0.015)
					self.RX_ACK_SEND=True
					self.collision=True
				else:
					print"PROBE_LEVEL", self.probe.level()
					print "THRESHOLD :", self.threshold
					#time.sleep(0.015)
					self.RX_ACK_SEND=True
		else:
			print "noting found"
			self.i=self.i+1
			print "I :",self.i
					
		
		if(self.RX_ACK_SEND==True):
			if(time.time()>self.rx_time+0.015):
				if(self.success==True):
					self.send_pkt_phy("####",ord(msg_str[PKT_INDEX_SEQ]),ord(msg_str[PKT_INDEX_SRC]),ACK_PKT_SUC)
					self.success=False
				elif(self.collision==True):
					self.send_pkt_phy("####",222,BROADCAST_ADDR,ACK_PKT_COL)
					self.collision=False
				else:
					self.send_pkt_phy("####",000,BROADCAST_ADDR,ACK_PKT_IDL)
			self.RX_ACK_SEND=False
			self.RX_PILOT_SEND=True
		#if(time.time()>self.pilot_tx_time+0.05):
			
	
	#post msg data to phy port- msg is string
	def send_pkt_phy(self,msg,pkt_cnt,pkt_src,protocol_id):
		#Framing MAC Info
		if(protocol_id==ACK_PKT_SUC):
			print "Transmitting SUCCESS ACK no. ",pkt_cnt 
		elif(protocol_id==ACK_PKT_COL):
			print "Transmitting COLLISION ACK no. ",pkt_cnt 
		elif(protocol_id==ACK_PKT_IDL):
			print "Transmitting IDLE ACK no. ",pkt_cnt 
		else:
			print "Transmitting PILOT ",pkt_cnt
			#print "PILOT",msg
		
		pkt_str=chr(pkt_src)+chr(self.source_addr)+chr(protocol_id)+chr(pkt_cnt)+msg

		#get a reference counted buffer to pass downstream
		buff = self.get_output_buffer(PHY_PORT)
		buff.offset = 0
		buff.length = len(pkt_str)
		buff.get()[:] = numpy.fromstring(pkt_str, numpy.uint8)
		self.post_output_msg(PHY_PORT,gras.PacketMsg(buff))

	def cs_busy(self):
		return self.probe.level()>self.threshold
