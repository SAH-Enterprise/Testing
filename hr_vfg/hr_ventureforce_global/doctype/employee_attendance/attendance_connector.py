from __future__ import unicode_literals
import frappe
from frappe import utils
from frappe import throw, _

import sys
import time
from zk import ZK, const
from datetime import datetime, timedelta
from frappe.utils import (
	date_diff,
	add_months,
	get_datetime,
	today,
	getdate,
	add_days,
	flt,
	get_last_day,
	cstr,
	now_datetime,
)
import calendar
from frappe.utils.background_jobs import enqueue
from requests import request
import json
from datetime import datetime
from datetime import timedelta


def _log_attendance_sync_error(context, exc, ip=None, port=None):
	"""Log machine sync failures with a short title (Error Log method max 140 chars)."""
	device = f"{ip}:{port}" if ip else "unknown"
	frappe.log_error(
		title=f"Attendance Sync: {context}"[:140],
		message=f"Device: {device}\nError: {exc}\n\n{frappe.get_traceback()}",
	)


@frappe.whitelist()
def get_attendance_long(**args):
	if not args:
		args = frappe.local.form_dict
	"Enqueue longjob for taking backup to dropbox"
	enqueue("hr_vfg.hr_ventureforce_global.doctype.employee_attendance.attendance_connector.execute_job", 
	 queue='long', timeout=8000,args=args)
	
	frappe.msgprint(_("Queued for biometric attendance. It may take a few minutes to an hour."))
@frappe.whitelist()
def execute_job(args):
	hr_settings = frappe.get_single('V HR Settings')
	for machine in hr_settings.attendance_machine:
		if machine.type == 'In':
			get_checkins(args,machine.ip,machine.port,machine.password)
		elif machine.type == "Out":
			get_checkouts(args,machine.ip,machine.port,machine.password)
		else:
			get_checkins_checkouts(args,machine.ip,machine.port,machine.password)

def get_checkins(args=None, ip=None, port=None,password=0):
	conn = None
	if not args:
		args = {"from_date":"2022-01-01","to_date":today()}
	emp_list = [] #110.93.236.48
	if not password:
		password = 0
	zk = ZK(ip, port=int(port), timeout=1500, password=password, force_udp=False, ommit_ping=True)
	frappe.log_error("Starting in..","Attendance hook test")
	try:
		conn = zk.connect()
		if conn:
			users = conn.get_users()
			if users:
				for u in users:
					#print(u)
					pass

			attendance = conn.get_attendance()
			print("getting attendance data")
			
			if attendance:
				#print(attendance)
				
				attendance_dict={}
				condition1 =""
				condition2=""
				biometric_list=[]
				b_filters = {}
				if args.get("employee"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}')".format(args.get("employee"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}')".format(args.get("employee"))
					b_filters["name"]=args.get("employee")
				if args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where department='{0}')".format(args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where department='{0}')".format(args.get("department"))
					b_filters["department"]=args.get("department")
				if args.get("employee") and args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))

				B_r = frappe.db.get_all("Employee",filters=b_filters,fields=["biometric_id"])
				for bid in B_r:
					biometric_list.append(bid.biometric_id)
				frappe.db.sql(""" delete from `tabAttendance Logs` where attendance_date >= %s and attendance_date <= %s and ip=%s {0} """.format(condition2), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				frappe.db.sql(""" update `tabEmployee Attendance Table` set check_in_1=NULL,  late_sitting=NULL, night_switch=0 where date >= %s and date <= %s and ip=%s and type!="Adjustment"{0} """.format(condition1), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				print(str(biometric_list))
				#frappe.log_error(len(attendance))
				for attend1 in attendance:
					if getdate(str(attend1).split()[3]) < getdate(args.get("from_date")) or getdate(str(attend1).split()[3]) > getdate(args.get("to_date")):
						continue
					# if str(attend1).split()[1] == "405":
					# 		print("Found 1 a")
					if len(biometric_list) > 0:
						if str(attend1).split()[1] not in biometric_list:
							continue
					if attendance_dict.get(str(attend1).split()[1]):
						if attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3]):
							# attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["check in"]=str(attend1).split()[4]
							# attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["checkin string"]=str(attend1)
							pass
						else:
							attendance_dict.get(str(attend1).split()[1])[str(attend1).split()[3]]={
								"check in": str(attend1).split()[4],
								"checkin string":str(attend1)
							}
					else:
						attendance_dict[str(attend1).split()[1]]={
							str(attend1).split()[3] :{
								"check in": str(attend1).split()[4],
								"checkin string":str(attend1)
							}
						}
					
					

				import json
				for users in attendance_dict:
					print(users)
					for dates in attendance_dict[users]:
						try:
							date = dates
							check_in = attendance_dict[users][dates].get("check in")
							check_in_string = attendance_dict[users][dates].get("checkin string")
							
							if check_in:
									d_a = str(utils.today()) +" 8:30:0"
									d_b = str(utils.today()) +" 1:0:0"
									d_s = str(utils.today()) +" 23:59:00"
									d_c = str(date+" "+check_in)
									
									res = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
									biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check In'""", 
									(users, str(date), check_in))
									if res:
										
										atl = frappe.get_doc("Attendance Logs",res[0][0])
										atl.save()
									else:
										print("adding check in")
										doc1 = frappe.new_doc("Attendance Logs")
										doc1.attendance = check_in_string
										doc1.biometric_id= users
										doc1.attendance_date= str(date)
										doc1.attendance_time= str(check_in)
										doc1.type = "Check In"
										doc1.ip = ip+":"+port
										doc1.save(ignore_permissions=True)
							
						except:
							frappe.log_error(frappe.get_traceback(),"Attendance hook test")
				
	except Exception as e:
		_log_attendance_sync_error("Check In", e, ip, port)
	finally:
		if conn:
			conn.disconnect()

def check_time(attend1):
	t_biometric = str(attend1).split()[1]
	flg = False
	t_date = str(attend1).split()[3]
	employee = frappe.db.get_value("Employee", {"biometric_id": t_biometric}, "name")
	shift_ass = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"start_date": ["<=", getdate(t_date)],
			"end_date": [">=", getdate(t_date)],
		},
		fields=["*"],
	)
	if len(shift_ass) > 0:
		shift = shift_ass[0].shift_type
	else:
		shift_ass = frappe.get_all(
			"Shift Assignment",
			filters={"employee": employee, "start_date": ["<=", getdate(t_date)]},
			fields=["*"],
		)
	if len(shift_ass) > 0:
		shift = shift_ass[0].shift_type
		shift_doc = frappe.get_doc("Shift Type", shift)
		s_type = shift_doc.shift_type
		t_check_out = str(attend1).split()[4]
		t_check_out_f_f = timedelta(
			hours=int(t_check_out.split(":")[0]), minutes=int(t_check_out.split(":")[1])
		)
		shift_start_t = timedelta(
			hours=int(str(shift_doc.start_time).split(":")[0]),
			minutes=int(str(shift_doc.start_time).split(":")[1]),
		)
		if t_check_out_f_f < shift_start_t:
			prev_date = add_days(getdate(t_date), -1)
			return True, prev_date
		return True, False

	return False, False
def get_checkouts(args=None,ip=None, port=None,password=0):
	conn = None
	emp_list = [] #110.93.236.48
	if not args:
		args = {"from_date":"2023-03-01","to_date":today()}
	if not password:
		password = 0
	zk = ZK(ip, port=int(port), timeout=1500, password=password, force_udp=False, ommit_ping=True)
	frappe.log_error("Starting out now","Attendance hook test")
	try:
		conn = zk.connect()
		if conn:
			users = conn.get_users()
			if users:
				for u in users:
					#print(u)
					pass

			attendance = conn.get_attendance()
			print("getting attendance data")
			#print(attendance)
			if attendance:
				#print(attendance)
				
				attendance_dict={}
				condition1 =""
				condition2=""
				biometric_list=[]
				b_filters = {}
				if args.get("employee"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}')".format(args.get("employee"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}')".format(args.get("employee"))
					b_filters["name"]=args.get("employee")
				if args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where department='{0}')".format(args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where department='{0}')".format(args.get("department"))
					b_filters["department"]=args.get("department")
				if args.get("employee") and args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))

				B_r = frappe.db.get_all("Employee",filters=b_filters,fields=["biometric_id"])
				for bid in B_r:
					biometric_list.append(bid.biometric_id)
				frappe.db.sql(""" delete from `tabAttendance Logs` where attendance_date >= %s and attendance_date <= %s and ip=%s {0} """.format(condition2), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				frappe.db.sql(""" update `tabEmployee Attendance Table` set check_out_1=NULL, late_sitting=NULL, night_switch=0 where date >= %s and date <= %s and ip=%s and type!="Adjustment"{0} """.format(condition1), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				for attend1 in attendance:
					if getdate(str(attend1).split()[3]) < getdate(args.get("from_date")) or getdate(str(attend1).split()[3]) > getdate(args.get("to_date")):
						continue
					if len(biometric_list) > 0:
						if str(attend1).split()[1] not in biometric_list:
							continue
					if attendance_dict.get(str(attend1).split()[1]):
						if attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3]):
							shift, prev_date = check_time(attend1)
							if shift:
									if prev_date:
										if attendance_dict.get(str(attend1).split()[1]).get(str(prev_date)):
											attendance_dict.get(str(attend1).split()[1]).get(str(prev_date))["check out"]=str(attend1).split()[4]
											attendance_dict.get(str(attend1).split()[1]).get(str(prev_date))["checkout string"]=str(attend1)
										else:
											attendance_dict[str(attend1).split()[1]]={
												str(prev_date) :{
													"check out": str(attend1).split()[4],
													"checkout string":str(attend1)
												}
											}
									else:
										flg = True

							else: 
								flg = True
							
							if flg:
								attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["check out"]=str(attend1).split()[4]
								attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["checkout string"]=str(attend1)
							print("done")
						else:
							shift, prev_date = check_time(attend1)
							if prev_date:
								attendance_dict.get(str(attend1).split()[1])[str(prev_date)]={
									"check out": str(attend1).split()[4],
									"checkout string":str(attend1)
								}
							else:
								attendance_dict.get(str(attend1).split()[1])[str(attend1).split()[3]]={
									"check out": str(attend1).split()[4],
									"checkout string":str(attend1)
								}
					else:
						
						shift, prev_date = check_time(attend1)
						if prev_date:
							attendance_dict[str(attend1).split()[1]]={
								str(prev_date) :{
									"check out": str(attend1).split()[4],
									"checkout string":str(attend1)
								}
							}
						else:
							attendance_dict[str(attend1).split()[1]]={
								str(attend1).split()[3] :{
									"check out": str(attend1).split()[4],
									"checkout string":str(attend1)
								}
							}
					
					

				import json
				#print(attendance_dict)
				for users in attendance_dict:
					print(users)
					for dates in attendance_dict[users]:
						try:
							date = dates
							check_in = attendance_dict[users][dates].get("check in")
							check_in_string = attendance_dict[users][dates].get("checkin string")
							check_out = attendance_dict[users][dates].get("check out")
							check_out_string = attendance_dict[users][dates].get("checkout string")
							
							check_in = None
							temp_chk_in = None
							
							if check_out:
									
									if check_in:
										x = datetime.strptime(
                        					str(temp_chk_in), '%H:%M:%S').time()
										y = datetime.strptime(
                        					str(check_out), '%H:%M:%S').time()
										hi,mi,si = str(x).split(':')
										ho,mo,so = str(y).split(':')
										diff_time = timedelta(hours=0, minutes=30, seconds=0)
										
										if (timedelta(hours=float(ho), minutes=float(mo), seconds=float(so))-timedelta(hours=float(hi), minutes=float(mi), seconds=float(si))) < diff_time:
											continue

									res = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
									biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check Out'""", 
									(users, str(date), check_out))
									if res:
										
										atl = frappe.get_doc("Attendance Logs",res[0][0])
										atl.save()
									else:
										print("adding check out")
										doc2 = frappe.new_doc("Attendance Logs")
										doc2.attendance = check_out_string
										doc2.biometric_id= users
										doc2.attendance_date= str(date)
										doc2.attendance_time= str(check_out)
										doc2.type = "Check Out"
										doc2.ip = '182.184.121.132:4371'
										doc2.save(ignore_permissions=True)
						except:
							frappe.log_error(frappe.get_traceback(),"Attendance hook test")
				
				
	except Exception as e:
		_log_attendance_sync_error("Check Out", e, ip, port)
	finally:
		if conn:
			conn.disconnect()


def get_checkins_checkouts(args=None,ip=None, port=None,password=0):
	conn = None
	emp_list = [] #110.93.236.48
	if not args:
		args = {"from_date":"2023-03-01","to_date":today()}
	if not password:
		password = 0
	zk = ZK(ip, port=int(port), timeout=1500, password=password, force_udp=False, ommit_ping=True)
	frappe.log_error("Starting in/out..","Attendance hook test")
	try:
		conn = zk.connect()
		if conn:
			users = conn.get_users()
			if users:
				for u in users:
					#print(u)
					pass

			attendance = conn.get_attendance()
			print("getting attendance data")
			#print(attendance)
			if attendance:
				#print(attendance)
				
				attendance_dict={}
				condition1 =""
				condition2=""
				biometric_list=[]
				b_filters = {}
				if args.get("employee"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}')".format(args.get("employee"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}')".format(args.get("employee"))
					b_filters["name"]=args.get("employee")
				if args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where department='{0}')".format(args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where department='{0}')".format(args.get("department"))
					b_filters["department"]=args.get("department")
				if args.get("employee") and args.get("department"):
					condition1=" and parent in (select name from `tabEmployee Attendance` where employee='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))
					condition2=" and biometric_id in (select biometric_id from `tabEmployee` where name='{0}' and department='{1}')".format(args.get("employee"),args.get("department"))

				B_r = frappe.db.get_all("Employee",filters=b_filters,fields=["biometric_id"])
				for bid in B_r:
					biometric_list.append(bid.biometric_id)
				frappe.db.sql(""" delete from `tabAttendance Logs` where attendance_date >= %s and attendance_date <= %s and ip=%s {0} """.format(condition2), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				frappe.db.sql(""" update `tabEmployee Attendance Table` set check_in_1 = NULL, check_out_1=NULL, late_sitting=NULL, night_switch=0 where date >= %s and date <= %s and ip=%s and type!="Adjustment"{0} """.format(condition1), (args.get("from_date"),args.get("to_date"),ip+":"+port))
				for attend1 in attendance:
					if getdate(str(attend1).split()[3]) < getdate(args.get("from_date")) or getdate(str(attend1).split()[3]) > getdate(args.get("to_date")):
						continue
					if len(biometric_list) > 0:
						if str(attend1).split()[1] not in biometric_list:
							continue
					if attendance_dict.get(str(attend1).split()[1]):
						if attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3]):
							t_biometric = str(attend1).split()[1]
							flg = False
							t_date = str(attend1).split()[3]
							employee = frappe.db.get_value("Employee",{"biometric_id":t_biometric},"name")
							shift_ass = frappe.get_all("Shift Assignment", filters={'employee': employee,
                                                                            'start_date': ["<=", getdate(t_date)],'end_date': [">=", getdate(t_date)]}, fields=["*"])
							if len(shift_ass) > 0:
								shift = shift_ass[0].shift_type
							else:
								shift_ass = frappe.get_all("Shift Assignment", filters={'employee': employee,
																					'start_date': ["<=", getdate(t_date)]}, fields=["*"])
							if len(shift_ass) > 0:
									shift = shift_ass[0].shift_type
									shift_doc = frappe.get_doc("Shift Type", shift)
									s_type = shift_doc.shift_type
									t_check_out = str(attend1).split()[4]
									t_check_out_f_f = timedelta(hours=int(t_check_out.split(":")[0]),minutes=int(t_check_out.split(":")[1]))
									shift_start_t = timedelta(hours=int(str(shift_doc.start_time).split(":")[0]),minutes=int(str(shift_doc.start_time).split(":")[1]))
									if t_check_out_f_f < shift_start_t:
										prev_date = add_days(getdate(t_date),-1)
										if attendance_dict.get(str(attend1).split()[1]).get(str(prev_date)):
											attendance_dict.get(str(attend1).split()[1]).get(str(prev_date))["check out"]=str(attend1).split()[4]
											attendance_dict.get(str(attend1).split()[1]).get(str(prev_date))["checkout string"]=str(attend1)
										else:
											attendance_dict[str(attend1).split()[1]]={
												str(prev_date) :{
													"check out": str(attend1).split()[4],
													"checkout string":str(attend1)
												}
											}
									else:
										flg = True

							else: 
								flg = True
							
							if flg:
								attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["check out"]=str(attend1).split()[4]
								attendance_dict.get(str(attend1).split()[1]).get(str(attend1).split()[3])["checkout string"]=str(attend1)
							print("done")
						else:
							attendance_dict.get(str(attend1).split()[1])[str(attend1).split()[3]]={
								"check in": str(attend1).split()[4],
								"checkin string":str(attend1)
							}
					else:
						attendance_dict[str(attend1).split()[1]]={
							str(attend1).split()[3] :{
								"check in": str(attend1).split()[4],
								"checkin string":str(attend1)
							}
						}
					
					

				import json
				#print(attendance_dict)
				for users in attendance_dict:
					print(users)
					for dates in attendance_dict[users]:
						try:
							date = dates
							check_in = attendance_dict[users][dates].get("check in")
							check_in_string = attendance_dict[users][dates].get("checkin string")
							check_out = attendance_dict[users][dates].get("check out")
							check_out_string = attendance_dict[users][dates].get("checkout string")
							
							if check_in:
									d_a = str(utils.today()) +" 8:30:0"
									d_b = str(utils.today()) +" 1:0:0"
									d_s = str(utils.today()) +" 23:59:00"
									d_c = str(date+" "+check_in)
									temp_chk_in = check_in

									res = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
									biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check In'""", 
									(users, str(date), check_in))
									if res:
										
										atl = frappe.get_doc("Attendance Logs",res[0][0])
										atl.save()
									else:
										print("adding check in")
										doc1 = frappe.new_doc("Attendance Logs")
										doc1.attendance = check_in_string
										doc1.biometric_id= users
										doc1.attendance_date= str(date)
										doc1.attendance_time= str(check_in)
										doc1.type = "Check In"
										doc1.ip = ip+":"+port
										doc1.save()
							if check_out:
									
									if check_in:
										x = datetime.strptime(
                        					str(temp_chk_in), '%H:%M:%S').time()
										y = datetime.strptime(
                        					str(check_out), '%H:%M:%S').time()
										hi,mi,si = str(x).split(':')
										ho,mo,so = str(y).split(':')
										diff_time = timedelta(hours=0, minutes=30, seconds=0)
										
										if (timedelta(hours=float(ho), minutes=float(mo), seconds=float(so))-timedelta(hours=float(hi), minutes=float(mi), seconds=float(si))) < diff_time:
											continue

									
									d_a = str(utils.today()) +" 8:30:0"
									d_b = str(utils.today()) +" 1:0:0"
									d_s = str(utils.today()) +" 23:59:00"
									d_c = str(date+" "+check_out)

									res = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
									biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check Out'""", 
									(users, str(date), check_out))
									if res:
										
										atl = frappe.get_doc("Attendance Logs",res[0][0])
										atl.save()
									else:
										print("adding check out")
										doc2 = frappe.new_doc("Attendance Logs")
										doc2.attendance = check_out_string
										doc2.biometric_id= users
										doc2.attendance_date= str(date)
										doc2.attendance_time= str(check_out)
										doc2.type = "Check Out"
										doc2.ip = ip+":"+port
										doc2.save()
						except:
							frappe.log_error(frappe.get_traceback(),"Attendance hook test")
				
				
	except Exception as e:
		_log_attendance_sync_error("Check In/Out", e, ip, port)
	finally:
		if conn:
			conn.disconnect()


@frappe.whitelist()
def get_attendance_from_api(date):
	response = request(method="GET", url="""https://api.ubiattendance.com/attendanceservice/getempattendance?apikey==AlVGhUVup0cNFjWadVb4xmVwolNZpmTXJmVKJnUrRWYWZFcHZVMotmVrlTUTxmWOJ1MCl1VrZ1dWdlRzpVRax2VtJ1RWJDdPFWMWhlVtRHbW1GaHlFM4gXTHZEWWtmWXVlaGVVVB1TP&Attendancedate={0} 
		""".format(date))
	response.raise_for_status()
	data = json.loads(response.text.split("]")[0]+"]")
	for item in data:
		chk_in = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
			biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check In'""", 
									(item["Employeecode"], item["attendancedate"], item["Timein"]))
		if not chk_in:
			#add checkin
			checkin = frappe.new_doc("Attendance Logs")
			checkin.attendance = "&lt;Attendance&gt;: {0} : {1} {2} (1, 1)".format(item["Employeecode"],item["attendancedate"],item["Timein"])
			checkin.biometric_id= item["Employeecode"]
			checkin.attendance_date= item["attendancedate"]
			checkin.attendance_time= item["Timein"]
			checkin.type = "Check In"
			checkin.ip = 'from_rest_api'
			checkin.save()

		else:
			doc = frappe.get_doc("Attendance Logs",chk_in[0][0])
			doc.attendance = "&lt;Attendance&gt;: {0} : {1} {2} (1, 1)".format(item["Employeecode"],item["attendancedate"],item["Timein"])
			doc.biometric_id= item["Employeecode"]
			doc.attendance_date= item["attendancedate"]
			doc.attendance_time= item["Timein"]
			doc.type = "Check In"
			doc.ip = 'from_rest_api'
			doc.save()



		chk_out = frappe.db.sql(""" select name, biometric_id from `tabAttendance Logs` where 
									biometric_id=%s and attendance_date=%s and attendance_time=%s and type='Check Out'""", 
									(item["Employeecode"], item["attendancedate"], item["Timeout"]))
		if not chk_out:
			#add chkout
			chkout = frappe.new_doc("Attendance Logs")
			chkout.biometric_id= item["Employeecode"]
			chkout.attendance = "&lt;Attendance&gt;: {0} : {1} {2} (1, 1)".format(item["Employeecode"],item["attendancedate"],item["Timeout"])
			chkout.attendance_date= item["attendancedate"]
			chkout.attendance_time= item["Timeout"]
			chkout.type = "Check Out"
			chkout.ip = 'from_rest_api'
			chkout.save()

		else:
			doc = frappe.get_doc("Attendance Logs",chk_out[0][0])
			doc.attendance = "&lt;Attendance&gt;: {0} : {1} {2} (1, 1)".format(item["Employeecode"],item["attendancedate"],item["Timeout"])
			doc.biometric_id= item["Employeecode"]
			doc.attendance_date= item["attendancedate"]
			doc.attendance_time= item["Timeout"]
			doc.type = "Check Out"
			doc.ip = 'from_rest_api'
			doc.save()

	return "done"
		

@frappe.whitelist()
def get_attendance_from_hook():
	frappe.log_error("Fetchhing","BGHOOK")
	args={
		"from_date":add_days(today(),-1),
		"to_date":getdate(today()),
	}
	get_attendance_long(**args)


LIVE_SYNC_LOCK_KEY = "attendance_live_sync_running"
LIVE_SYNC_LOCK_TTL = 120
LIVE_SYNC_TARGET_CYCLE_SECONDS = 25  # ideal target; device full-log download is the floor
LIVE_SYNC_MIN_SLEEP_SECONDS = 1  # poll again immediately after each pull
LIVE_SYNC_JOB_ID = "attendance_fast_sync_daemon"
LIVE_SYNC_LEGACY_JOB_IDS = ("attendance_live_sync_daemon", "attendance_live_sync_loop")
LIVE_SYNC_DAEMON_SECONDS = 55 * 60  # run ~55 minutes then exit; watchdog restarts
ZK_USERS_REFRESH_KEY = "attendance_zk_users_refreshed_at"
ZK_USERS_REFRESH_SECONDS = 30 * 60
MACHINE_STATUS_CACHE_KEY = "attendance_machine_integration_status"
# Live-capture over WAN rarely delivers punches and delays the next full pull — keep off by default.
LIVE_CAPTURE_ENABLED = False
LIVE_CAPTURE_SECONDS = 12


def _cancel_stuck_live_sync_jobs():
	"""Remove stale RQ live-sync jobs that block restart."""
	from frappe.utils.background_jobs import create_job_id, get_queue

	job_ids = (LIVE_SYNC_JOB_ID,) + LIVE_SYNC_LEGACY_JOB_IDS
	for queue_name in ("short", "long", "default"):
		try:
			q = get_queue(queue_name)
			for raw_id in job_ids:
				jid = create_job_id(raw_id)
				job = q.fetch_job(jid)
				if not job:
					from rq.job import Job
					from frappe.utils.background_jobs import get_redis_conn

					try:
						job = Job.fetch(jid, connection=get_redis_conn())
					except Exception:
						job = None
				if job:
					try:
						job.cancel()
					except Exception:
						pass
					try:
						job.delete()
					except Exception:
						pass
		except Exception:
			pass


def ensure_attendance_live_sync_loop():
	"""Minute watchdog: keep fast live-poll daemon on the short queue."""
	from frappe.utils.background_jobs import enqueue, is_job_enqueued

	if is_job_enqueued(LIVE_SYNC_JOB_ID):
		return {"status": "running"}

	_cancel_stuck_live_sync_jobs()
	enqueue(
		"hr_vfg.hr_ventureforce_global.doctype.employee_attendance.attendance_connector.run_attendance_live_sync_daemon",
		queue="short",
		timeout=LIVE_SYNC_DAEMON_SECONDS + 120,
		job_id=LIVE_SYNC_JOB_ID,
		deduplicate=True,
	)
	return {"status": "started"}


def _live_capture_worker(machine, seconds, event_queue, stop_event):
	"""Background thread: stream realtime punches from one ZK device."""
	import time as _time

	ip = machine.ip
	port = int(machine.port)
	password = machine.password or 0
	conn = None
	try:
		zk = ZK(
			ip,
			port=port,
			timeout=10,
			password=password,
			force_udp=False,
			ommit_ping=True,
		)
		conn = zk.connect()
		if not conn:
			return
		t_end = _time.time() + seconds
		for attend in conn.live_capture(new_timeout=2):
			if stop_event.is_set() or _time.time() >= t_end:
				conn.end_live_capture = True
				break
			if attend is None:
				continue
			event_queue.put((machine, attend))
	except Exception as e:
		event_queue.put(("error", ip, port, cstr(e)))
	finally:
		if conn:
			try:
				conn.end_live_capture = True
				conn.disconnect()
			except Exception:
				pass


def _insert_live_capture_event(machine, attend):
	"""Insert one realtime punch; returns True if a new Attendance Log was created."""
	biometric_id, att_date, att_time, raw = _parse_zk_attendance_row(attend)
	if not biometric_id or not att_date or not att_time:
		return False
	ip_key = f"{machine.ip}:{machine.port}"
	log_type = _machine_log_type(machine.type, attend)
	created = _insert_attendance_log_if_missing(
		biometric_id, str(att_date), str(att_time), log_type, ip_key, raw
	)
	if created:
		frappe.db.commit()
	return created


def _live_listen_machines(machines, seconds=20):
	"""
	Listen for realtime punches on all machines in parallel.
	Inserts arrive as events (usually <2s), covering the gap between full polls.
	"""
	import queue
	import threading
	import time as _time

	if not machines or seconds <= 0:
		return 0

	event_queue = queue.Queue()
	stop_event = threading.Event()
	threads = []
	for machine in machines:
		t = threading.Thread(
			target=_live_capture_worker,
			args=(machine, seconds, event_queue, stop_event),
			daemon=True,
		)
		t.start()
		threads.append(t)

	created = 0
	t_end = _time.time() + seconds + 2
	alive = True
	while _time.time() < t_end and alive:
		try:
			item = event_queue.get(timeout=0.5)
		except queue.Empty:
			alive = any(t.is_alive() for t in threads)
			continue
		if isinstance(item, tuple) and item and item[0] == "error":
			_, ip, port, err = item
			_log_attendance_sync_error("Live Capture", err, ip, port)
			continue
		machine, attend = item
		try:
			if _insert_live_capture_event(machine, attend):
				created += 1
		except Exception as e:
			_log_attendance_sync_error("Live Capture Insert", e, machine.ip, machine.port)

	stop_event.set()
	for t in threads:
		t.join(timeout=5)
	return created


def run_attendance_live_sync_daemon():
	"""
	Continuously pull both machines in parallel with almost no idle gap.

	Hard floor: ZK only supports full attendance download (~20-35s per device over
	WAN). Live-capture is optional and off by default — on this network it usually
	does not push punches and only delayed the next poll (causing 1–1.5 min lag).
	"""
	import time

	deadline = time.time() + LIVE_SYNC_DAEMON_SECONDS
	while time.time() < deadline:
		t0 = time.time()
		try:
			sync_attendance_logs_live(reschedule=False)
		except Exception as e:
			_log_attendance_sync_error("Live Sync Daemon", e)

		if LIVE_CAPTURE_ENABLED:
			try:
				hr_settings = frappe.get_single("V HR Settings")
				machines = [
					m
					for m in (hr_settings.get("attendance_machine") or [])
					if m.ip and m.port
				]
				_live_listen_machines(machines, seconds=LIVE_CAPTURE_SECONDS)
			except Exception as e:
				_log_attendance_sync_error("Live Capture Window", e)

		elapsed = time.time() - t0
		# Re-poll immediately; only a tiny pause to avoid tight CPU spin on errors.
		time.sleep(LIVE_SYNC_MIN_SLEEP_SECONDS if elapsed > 5 else 2)


def _parse_zk_attendance_row(attend):
	"""Return (biometric_id, date_str, time_str, raw_str) from a ZK attendance record."""
	raw = str(attend)
	biometric_id = None
	att_date = None
	att_time = None

	user_id = getattr(attend, "user_id", None)
	timestamp = getattr(attend, "timestamp", None)
	if user_id is not None and timestamp is not None:
		biometric_id = str(user_id).strip()
		if isinstance(timestamp, datetime):
			att_date = timestamp.strftime("%Y-%m-%d")
			att_time = timestamp.strftime("%H:%M:%S")
		else:
			ts = get_datetime(timestamp)
			att_date = ts.strftime("%Y-%m-%d")
			att_time = ts.strftime("%H:%M:%S")
	else:
		parts = raw.split()
		if len(parts) >= 5:
			biometric_id = str(parts[1]).strip()
			att_date = str(parts[3]).strip()
			att_time = str(parts[4]).strip()

	return biometric_id, att_date, att_time, raw


def _machine_log_type(machine_type, attend):
	machine_type = (machine_type or "Both").strip()
	if machine_type == "In":
		return "Check In"
	if machine_type == "Out":
		return "Check Out"

	# Both: prefer device punch/status when available (0/1 common for in/out).
	punch = getattr(attend, "punch", None)
	status = getattr(attend, "status", None)
	value = punch if punch is not None else status
	try:
		value = int(value)
	except (TypeError, ValueError):
		value = None
	if value in (0, 4):
		return "Check In"
	if value in (1, 5):
		return "Check Out"
	return "Punch"


def _insert_attendance_log_if_missing(biometric_id, att_date, att_time, log_type, ip_key, raw):
	exists = frappe.db.exists(
		"Attendance Logs",
		{
			"biometric_id": biometric_id,
			"attendance_date": att_date,
			"attendance_time": att_time,
			"type": log_type,
			"ip": ip_key,
		},
	)
	if exists:
		return False

	# Fallback: same punch already stored under another type label.
	exists_any = frappe.db.sql(
		"""
		select name from `tabAttendance Logs`
		where biometric_id=%s and attendance_date=%s and attendance_time=%s and ip=%s
		limit 1
		""",
		(biometric_id, att_date, att_time, ip_key),
	)
	if exists_any:
		return False

	doc = frappe.new_doc("Attendance Logs")
	doc.attendance = raw
	doc.biometric_id = biometric_id
	doc.attendance_date = att_date
	doc.attendance_time = att_time
	doc.type = log_type
	doc.ip = ip_key
	doc.flags.skip_employee_attendance = True
	doc.insert(ignore_permissions=True)
	return True


def _record_machine_integration_status(machines_status, created_total=0):
	"""Persist last real machine integration result for Punch Portal."""
	online = sum(1 for m in machines_status if m.get("online"))
	payload = {
		"checked_at": str(now_datetime()),
		"integrated": online > 0 and online == len(machines_status) and len(machines_status) > 0,
		"partial": online > 0 and online < len(machines_status),
		"online_count": online,
		"total_count": len(machines_status),
		"created": created_total,
		"machines": machines_status,
	}
	# keep long enough for portal polling
	frappe.cache().set_value(MACHINE_STATUS_CACHE_KEY, payload, expires_in_sec=60 * 30)
	return payload


def _should_refresh_zk_users():
	cache = frappe.cache()
	if cache.get_value(ZK_USERS_REFRESH_KEY):
		return False
	cache.set_value(ZK_USERS_REFRESH_KEY, 1, expires_in_sec=ZK_USERS_REFRESH_SECONDS)
	return True


def _fetch_zk_attendance_raw(ip, port, password=0, refresh_users=False):
	"""
	Device I/O only (thread-safe). Downloads attendance; optionally user names.
	ZK has no date filter — full log download is required (~20s on large devices).
	"""
	import time as _time

	ip_key = f"{ip}:{port}"
	result = {
		"ip": ip,
		"port": str(port),
		"ip_key": ip_key,
		"online": False,
		"integrated": False,
		"error": "",
		"attendance": [],
		"users": None,
		"fetch_seconds": 0,
		"record_count": 0,
	}
	conn = None
	t0 = _time.time()
	try:
		zk = ZK(
			ip,
			port=int(port),
			timeout=25,
			password=password or 0,
			force_udp=False,
			ommit_ping=True,
		)
		conn = zk.connect()
		if not conn:
			result["error"] = "Connect failed"
			return result
		result["online"] = True
		result["integrated"] = True
		if refresh_users:
			try:
				result["users"] = conn.get_users() or []
			except Exception:
				result["users"] = None
		attendance = conn.get_attendance() or []
		result["attendance"] = attendance
		result["record_count"] = len(attendance)
	except Exception as e:
		result["error"] = cstr(e)
	finally:
		if conn:
			try:
				conn.disconnect()
			except Exception:
				pass
		result["fetch_seconds"] = round(_time.time() - t0, 2)
	return result


def _existing_punch_keys(from_date, to_date, ip_keys):
	"""One query for yesterday+today punches instead of per-row exists checks."""
	if not ip_keys:
		return set()
	placeholders = ", ".join(["%s"] * len(ip_keys))
	rows = frappe.db.sql(
		f"""
		select biometric_id, attendance_date, attendance_time, ip
		from `tabAttendance Logs`
		where attendance_date between %s and %s
		  and ip in ({placeholders})
		""",
		[str(from_date), str(to_date), *ip_keys],
	)
	return {
		(cstr(bio), cstr(d), cstr(t), cstr(ip))
		for bio, d, t, ip in rows
	}


def _collect_window_punches(attendance, machine_type, ip_key, from_dt, to_dt):
	"""
	Walk newest→oldest (device log is ascending). Stop once older than from_dt.
	"""
	rows = []
	for attend in reversed(attendance or []):
		biometric_id, att_date, att_time, raw = _parse_zk_attendance_row(attend)
		if not biometric_id or not att_date or not att_time:
			continue
		try:
			row_date = getdate(att_date)
		except Exception:
			continue
		if row_date > to_dt:
			continue
		if row_date < from_dt:
			break
		rows.append(
			{
				"biometric_id": biometric_id,
				"attendance_date": str(att_date),
				"attendance_time": str(att_time),
				"type": _machine_log_type(machine_type, attend),
				"ip": ip_key,
				"raw": raw,
			}
		)
	return rows


def _sync_machine_attendance_logs_live(machine, from_date, to_date, refresh_users=False):
	"""Legacy single-machine path (kept for manual calls). Prefer parallel sync."""
	fetched = _fetch_zk_attendance_raw(
		machine.ip, machine.port, machine.password or 0, refresh_users=refresh_users
	)
	status = {
		"ip": fetched["ip"],
		"port": fetched["port"],
		"type": machine.type or "Both",
		"online": fetched["online"],
		"integrated": fetched["integrated"],
		"error": fetched["error"],
		"created": 0,
		"fetch_seconds": fetched["fetch_seconds"],
		"device_records": fetched["record_count"],
	}
	if fetched.get("users"):
		try:
			from hr_vfg.hr_ventureforce_global.punch_portal import remember_zk_users

			remember_zk_users(fetched["users"])
		except Exception:
			pass
	if not fetched["online"]:
		if fetched["error"]:
			_log_attendance_sync_error("Live Sync", fetched["error"], machine.ip, machine.port)
		return 0, status

	from_dt = getdate(from_date)
	to_dt = getdate(to_date)
	ip_key = fetched["ip_key"]
	candidates = _collect_window_punches(
		fetched["attendance"], machine.type, ip_key, from_dt, to_dt
	)
	existing = _existing_punch_keys(from_dt, to_dt, [ip_key])
	created = 0
	for row in candidates:
		key = (row["biometric_id"], row["attendance_date"], row["attendance_time"], row["ip"])
		if key in existing:
			continue
		if _insert_attendance_log_if_missing(
			row["biometric_id"],
			row["attendance_date"],
			row["attendance_time"],
			row["type"],
			row["ip"],
			row["raw"],
		):
			created += 1
			existing.add(key)
	status["created"] = created
	if created:
		frappe.db.commit()
	return created, status


@frappe.whitelist()
def sync_attendance_logs_live(reschedule=False):
	"""
	Near real-time poll: pull yesterday+today punches and insert missing
	Attendance Logs only (no delete / no full rebuild).

	Optimizations vs old path:
	- fetch In/Out machines in parallel (~22s wall vs ~45s sequential)
	- skip full user list most cycles
	- scan newest device rows only (sorted ascending log)
	- one bulk existence query for the date window
	"""
	import time as _time
	from concurrent.futures import ThreadPoolExecutor, as_completed

	cache = frappe.cache()
	if cache.get_value(LIVE_SYNC_LOCK_KEY):
		return {"status": "skipped", "reason": "already running"}

	cache.set_value(LIVE_SYNC_LOCK_KEY, 1, expires_in_sec=LIVE_SYNC_LOCK_TTL)
	created_total = 0
	machines_status = []
	t_job = _time.time()
	try:
		hr_settings = frappe.get_single("V HR Settings")
		machines = [
			m for m in (hr_settings.get("attendance_machine") or []) if m.ip and m.port
		]
		if not machines:
			_record_machine_integration_status([], 0)
			return {"status": "ok", "created": 0, "integrated": False, "seconds": 0}

		from_dt = getdate(add_days(today(), -1))
		to_dt = getdate(today())
		refresh_users = _should_refresh_zk_users()

		# Parallel device download (dominant cost ~20s each)
		fetched_by_key = {}
		with ThreadPoolExecutor(max_workers=max(1, len(machines))) as pool:
			futures = {
				pool.submit(
					_fetch_zk_attendance_raw,
					m.ip,
					m.port,
					m.password or 0,
					refresh_users,
				): m
				for m in machines
			}
			for fut in as_completed(futures):
				machine = futures[fut]
				try:
					fetched_by_key[f"{machine.ip}:{machine.port}"] = (machine, fut.result())
				except Exception as e:
					fetched_by_key[f"{machine.ip}:{machine.port}"] = (
						machine,
						{
							"ip": machine.ip,
							"port": str(machine.port),
							"ip_key": f"{machine.ip}:{machine.port}",
							"online": False,
							"integrated": False,
							"error": cstr(e),
							"attendance": [],
							"users": None,
							"fetch_seconds": 0,
							"record_count": 0,
						},
					)

		ip_keys = []
		all_candidates = []
		for machine in machines:
			key = f"{machine.ip}:{machine.port}"
			machine, fetched = fetched_by_key[key]
			status = {
				"ip": fetched["ip"],
				"port": fetched["port"],
				"type": machine.type or "Both",
				"online": fetched["online"],
				"integrated": fetched["integrated"],
				"error": fetched.get("error") or "",
				"created": 0,
				"fetch_seconds": fetched.get("fetch_seconds") or 0,
				"device_records": fetched.get("record_count") or 0,
			}
			if fetched.get("users"):
				try:
					from hr_vfg.hr_ventureforce_global.punch_portal import remember_zk_users

					remember_zk_users(fetched["users"])
				except Exception:
					pass
			if not fetched["online"]:
				if status["error"]:
					_log_attendance_sync_error(
						"Live Sync", status["error"], machine.ip, machine.port
					)
				machines_status.append(status)
				continue

			ip_keys.append(fetched["ip_key"])
			candidates = _collect_window_punches(
				fetched["attendance"], machine.type, fetched["ip_key"], from_dt, to_dt
			)
			status["_candidates"] = candidates
			machines_status.append(status)

		existing = _existing_punch_keys(from_dt, to_dt, ip_keys)
		touched_bios = set()
		for status in machines_status:
			candidates = status.pop("_candidates", [])
			created = 0
			for row in candidates:
				key = (
					row["biometric_id"],
					row["attendance_date"],
					row["attendance_time"],
					row["ip"],
				)
				if key in existing:
					continue
				if _insert_attendance_log_if_missing(
					row["biometric_id"],
					row["attendance_date"],
					row["attendance_time"],
					row["type"],
					row["ip"],
					row["raw"],
				):
					created += 1
					created_total += 1
					existing.add(key)
					touched_bios.add(row["biometric_id"])
			status["created"] = created

		if created_total:
			frappe.db.commit()
			try:
				from hr_vfg.hr_ventureforce_global.doctype.attendance_logs.attendance_logs import (
					apply_logs_to_employee_attendance,
				)

				apply_logs_to_employee_attendance(
					from_dt, to_dt, biometric_ids=list(touched_bios)
				)
			except Exception as e:
				_log_attendance_sync_error("Apply Logs To Sheets", e)

		integration = _record_machine_integration_status(machines_status, created_total)
		return {
			"status": "ok",
			"created": created_total,
			"integrated": integration.get("integrated"),
			"machines": machines_status,
			"seconds": round(_time.time() - t_job, 2),
		}
	except Exception as e:
		_log_attendance_sync_error("Live Sync Job", e)
		return {"status": "error", "message": str(e), "integrated": False}
	finally:
		cache.delete_value(LIVE_SYNC_LOCK_KEY)


@frappe.whitelist()
def email_report():
		from frappe.email.doctype.auto_email_report.auto_email_report import send_now
		auto_email_report = frappe.get_doc('Auto Email Report', "Daily Attendance")
		auto_email_report.update({
			"filters": """{."from.":\""""+str(getdate(today()))+"""\",\"to\":\""""+str(getdate(today()))+"""\"}"""
		})
		auto_email_report.save()
		send_now("Daily Attendance")

	