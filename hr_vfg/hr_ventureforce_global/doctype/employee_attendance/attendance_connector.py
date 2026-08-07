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
LIVE_SYNC_INTERVAL_SECONDS = 15
LIVE_SYNC_JOB_ID = "attendance_live_sync_daemon"
LIVE_SYNC_DAEMON_SECONDS = 50 * 60  # run ~50 minutes then exit; watchdog restarts


def _cancel_stuck_live_sync_jobs():
	"""Remove stale RQ scheduled/failed live-sync jobs that block restart."""
	from frappe.utils.background_jobs import create_job_id, get_queue

	for queue_name in ("short", "long", "default"):
		try:
			q = get_queue(queue_name)
			job_id = create_job_id(LIVE_SYNC_JOB_ID)
			# also clear the old broken enqueue_in job id
			legacy_id = create_job_id("attendance_live_sync_loop")
			for jid in (job_id, legacy_id):
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
	"""Minute watchdog: keep a live-poll daemon worker running."""
	from frappe.utils.background_jobs import enqueue, is_job_enqueued

	if is_job_enqueued(LIVE_SYNC_JOB_ID):
		return {"status": "running"}

	_cancel_stuck_live_sync_jobs()
	enqueue(
		"hr_vfg.hr_ventureforce_global.doctype.employee_attendance.attendance_connector.run_attendance_live_sync_daemon",
		queue="long",
		timeout=LIVE_SYNC_DAEMON_SECONDS + 120,
		job_id=LIVE_SYNC_JOB_ID,
		deduplicate=True,
	)
	return {"status": "started"}


def run_attendance_live_sync_daemon():
	"""Continuously poll machines every ~15s (replaces broken RQ enqueue_in loop)."""
	import time

	deadline = time.time() + LIVE_SYNC_DAEMON_SECONDS
	while time.time() < deadline:
		try:
			sync_attendance_logs_live(reschedule=False)
		except Exception as e:
			_log_attendance_sync_error("Live Sync Daemon", e)
		time.sleep(LIVE_SYNC_INTERVAL_SECONDS)


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


MACHINE_STATUS_CACHE_KEY = "attendance_machine_integration_status"


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


def _sync_machine_attendance_logs_live(machine, from_date, to_date):
	ip = machine.ip
	port = machine.port
	password = machine.password or 0
	ip_key = f"{ip}:{port}"
	conn = None
	created = 0
	status = {
		"ip": ip,
		"port": str(port),
		"type": machine.type or "Both",
		"online": False,
		"integrated": False,
		"error": "",
		"created": 0,
	}

	zk = ZK(
		ip,
		port=int(port),
		timeout=20,
		password=password,
		force_udp=False,
		ommit_ping=True,
	)
	try:
		conn = zk.connect()
		if not conn:
			status["error"] = "Connect failed"
			return created, status

		status["online"] = True
		status["integrated"] = True
		attendance = conn.get_attendance() or []
		from_dt = getdate(from_date)
		to_dt = getdate(to_date)

		for attend in attendance:
			biometric_id, att_date, att_time, raw = _parse_zk_attendance_row(attend)
			if not biometric_id or not att_date or not att_time:
				continue
			try:
				row_date = getdate(att_date)
			except Exception:
				continue
			if row_date < from_dt or row_date > to_dt:
				continue

			log_type = _machine_log_type(machine.type, attend)
			if _insert_attendance_log_if_missing(
				biometric_id, str(att_date), str(att_time), log_type, ip_key, raw
			):
				created += 1

		status["created"] = created
		if created:
			frappe.db.commit()
	except Exception as e:
		status["error"] = cstr(e)
		_log_attendance_sync_error("Live Sync", e, ip, port)
	finally:
		if conn:
			try:
				conn.disconnect()
			except Exception:
				pass

	return created, status


@frappe.whitelist()
def sync_attendance_logs_live(reschedule=False):
	"""
	Near real-time poll: pull yesterday+today punches and insert
	any missing rows into Attendance Logs only (no delete / no full rebuild).

	Runs as a short scheduled job (not a long-queue daemon) so Get Attendance
	jobs are not blocked.
	"""
	cache = frappe.cache()
	if cache.get_value(LIVE_SYNC_LOCK_KEY):
		return {"status": "skipped", "reason": "already running"}

	cache.set_value(LIVE_SYNC_LOCK_KEY, 1, expires_in_sec=LIVE_SYNC_LOCK_TTL)
	created_total = 0
	machines_status = []
	try:
		hr_settings = frappe.get_single("V HR Settings")
		machines = hr_settings.get("attendance_machine") or []
		if not machines:
			_record_machine_integration_status([], 0)
			return {"status": "ok", "created": 0, "integrated": False}

		args = {
			"from_date": add_days(today(), -1),
			"to_date": getdate(today()),
		}
		for machine in machines:
			if not machine.ip or not machine.port:
				continue
			created, status = _sync_machine_attendance_logs_live(
				machine, args["from_date"], args["to_date"]
			)
			created_total += created
			machines_status.append(status)

		integration = _record_machine_integration_status(machines_status, created_total)
		return {
			"status": "ok",
			"created": created_total,
			"integrated": integration.get("integrated"),
			"machines": machines_status,
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

	