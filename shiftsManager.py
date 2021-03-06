# -*- coding: utf-8 -*-
import base64
import calendar
import copy
import datetime
import io
import json
import mimetypes
import os
import random
import operator
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.MIMEText import MIMEText

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from httplib2 import Http
from oauth2client import client, file, tools

SCOPES = ['https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/calendar',
          'https://mail.google.com/	']

global shiftsSummary
shiftsSummary = ['תורנות בוקר', 'תורנות לילה', 'תורנות שבת']

# The precentage of all days in month that it fair to have difference between
# you and the minimal placement people
global fairnessLevel
fairnessLevel = 20

global NIGHT_TIME
NIGHT_TIME = 20

global placement
placement = {}

global unresolvedCount
unresolvedCount = 0

global SHIFT_POINTS
SHIFT_POINTS = [1, 2, 4]  # Day, night, weekend

global ITERATIONS_TIMES
ITERATIONS_TIMES = 1500


def initializeDays():
    today = datetime.datetime.now()

    month = today.month
    year = today.year

    if(today.month + 1 > 12):
        month = 1
        year = today.year + 1
    else:
        month += 1

    global daysRange
    daysRange = calendar.monthrange(year, month)

    # Datetime.date with isoweekday start with monday = 0
    global days
    dayArray = [datetime.datetime(year, month, day)
                for day in range(1, daysRange[1] + 1)]
    days = []

    for day in dayArray:
        # Weekend
        if(day.weekday() in [4, 5]):
            days.append(day)
        else:
            morningShift = copy.deepcopy(day)
            nightShift = copy.deepcopy(day)
            morningShift = morningShift.replace(hour=8)
            nightShift = nightShift.replace(hour=20)

            days.append(morningShift)
            days.append(nightShift)

def getShiftScore(shift):
    score = SHIFT_POINTS[0]
    if shift.hour == NIGHT_TIME:
        score = SHIFT_POINTS[1]
    elif shift.weekday() in [4, 5]:
        score = SHIFT_POINTS[2]

    return score

def recursiveBackTracking(day, index):

    i = 0
    random.shuffle(peoples)

    while(i < len(peoples)):
        isPlaceable = canBePlaced(day, peoples[i])
        if(isPlaceable):

            temp = copy.deepcopy(peoples[i])
            #placement[day] = peoples[i]
            placement[day] = temp

            score = getShiftScore(day)
            peoples[i]["Count"] += score

            if(index + 1 < len(days)):
                index += 1
                answer = recursiveBackTracking(days[index], index)
                if answer:
                    return answer
            else:
                return True
        i += 1
    if(i >= len(peoples)):
        placement[day] = "Unresolved"
        global unresolvedCount
        unresolvedCount += 1
        if(index + 1 < len(days)):
            index += 1
            return recursiveBackTracking(days[index], index)

    return False

# Check if people can be place in this day
def canBePlaced(day, people):

    # Check if he have constraint on this day
    if (day.day in people["Constraints"]):
        return False

    # If he has placed x days more then the lowest placed person then he cant
    # be placed this day.
    # X is the toal days in the month divided by the fairness level.
    # for example: if the fairness level is 10, and there is 30 days in the month
    # then the difference between you and the lowest can be 3 days.
    minPlacement = getMinimum()
    precentage = float(fairnessLevel) / 100
    if(people["Count"] > ((daysRange[1] * precentage) + minPlacement)):
        return False

    if(day.hour == NIGHT_TIME and people["canNights"] == "False"):
        return False

    if(day.weekday() in [4, 5] and people["canWeekend"] == "False"):
        return False

    return True

# Get the lowest placement count
def getMinimum():
    min = len(days) + 1
    for people in peoples:
        if(people["Count"] < min):
            min = people["Count"]
    return min

def getConstraintsFromDrive():
    service = getservice('drive', 'v3')
    file_id = 'X'
    request = service.files().export_media(fileId=file_id, mimeType='text/csv')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print "Download %d%%." % int(status.progress() * 100)

    rows = fh.getvalue().split("\r\n")

    COLS = rows[0].split(",")
    global CONSTRAINTS
    CONSTRAINTS = {"peoples": []}

    # i for rows, each row is a person in the csv
    for i in xrange(1, len(rows)):

        row = rows[i]
        CONSTRAINTS["peoples"].append({})

        # col for column in the csv.
        for col in xrange(len(row.split(","))):
            if COLS[col] == "Constraints":
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col].split(" ")

                # Check if there are no constraints.
                if not (len(CONSTRAINTS["peoples"][i - 1][COLS[col]]) == 1 and CONSTRAINTS["peoples"][i - 1][COLS[col]][0] == ''):
                    CONSTRAINTS["peoples"][i - 1][COLS[col]] = map(int, CONSTRAINTS["peoples"][i - 1][COLS[col]])
                else:
                    CONSTRAINTS["peoples"][i - 1][COLS[col]] = [0]

            elif COLS[col] == "Count":
                CONSTRAINTS["peoples"][i - 1][COLS[col]
                                              ] = int(row.split(",")[col])
            else:
                CONSTRAINTS["peoples"][i - 1][COLS[col]] = row.split(",")[col]

    print(CONSTRAINTS)

def sendInvite(bestRun):
    #store = file.Storage('token.json')
    #creds = store.get()
    #if not creds or creds.invalid:
    #    flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
    #    creds = tools.run_flow(flow, store)
    #service = build('calendar', 'v3', http=creds.authorize(Http()))

    service = getservice('calendar','v3')

    for dayIndex in xrange(len(days) - 1):
        if bestRun['placements'][days[dayIndex]] != 'Unresolved':
            if "@" in bestRun['placements'][days[dayIndex]]['Email']:
                eventObj = {}
                eventObj["start"] = {"dateTime": getDateString(
                    days[dayIndex]), "timeZone": "Asia/Jerusalem"}
                eventObj["end"] = {}
                eventObj["end"] = {"dateTime": getDateString(
                    days[dayIndex + 1]), "timeZone": "Asia/Jerusalem"}
                eventObj["attendees"] = [
                    {"email": bestRun['placements'][days[dayIndex]]['Email']}]
                eventObj["summary"] = shiftsSummary[getEventType(
                    days[dayIndex])]

                service.events().insert(calendarId='primary', body=eventObj).execute()

def getEventType(day):
    if day.weekday() in [4, 5]:
        return 2
    if str(day.hour) == '20':
        return 1
    if str(day.hour) == '8':
        return 0

def getDateString(date):
    hour = str(date.hour)
    day = str(date.day)
    month = str(date.month)
    if hour == "8":
        hour = "08"
    if len(day) == 1:
        day = "0" + day
    if len(month) == 1:
        month = "0" + month
    return str(date.year) + "-" + month + "-" + day + "T" + hour + ":00:00"

def sendMesseage(bestRun,path):
    body = ''
    for people in bestRun["peoples"]:
        body += people["Name"] + ":" + str(people["Count"]) + "\n"

    if bestRun['unresolved'] == 0:
        body += 'You got zero unresolved date to handle!'
    else:
        body += 'You got ' + str(bestRun['unresolved']) + ' unresolved date/s, you better handle them before publishing! \n'
        for day in days:
            if bestRun['placements'][day] == 'Unresolved':
                body += day.strftime('%d-%m-%Y')

    message = MIMEMultipart()
    msg = MIMEText(body)
    message['to'] = 'X'
    message['from'] = 'X'
    message['subject'] = str(days[0])
    message.attach(msg)

    content_type, encoding = mimetypes.guess_type(path)
    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    fp = open(path, 'rb')
    msg = MIMEBase(main_type, sub_type)
    msg.set_payload(fp.read())
    fp.close()
    filename = os.path.basename(path)
    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg)
    message = {'raw': base64.urlsafe_b64encode(message.as_string())}

    service = getservice('gmail','v1')
    message = (service.users().messages().send(userId='me', body=message).execute())
    print 'Message Id: %s' % message['id']

def createCSV(bestRun):
    headers = 'טלפון,שם,סוג,יום,תאריך'
    headers += '\n'
    content = ''
    for day in days:
        if bestRun['placements'][day] == 'Unresolved':
            content += 'Unresolved,Unresolved,'
            content += shiftsSummary[getEventType(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'
        else:
            content += bestRun['placements'][day]['Phone'] + ","
            content += bestRun['placements'][day]['Name'] + ","
            content += shiftsSummary[getEventType(day)] + ","
            content += day.strftime('%A') + ','
            content += day.strftime('%d-%m-%Y') + '\n'
    PATH = '/tmp/'
    PATH += days[0].strftime('%d-%m-%Y')
    PATH += '.csv'
    f = open(PATH,'w')
    f.write(headers + content)
    f.close()
    return PATH

def getservice(api,version):
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build(api, version, http=creds.authorize(Http()))
    return service

def utility(run):
    const = float(10)/ float(62)
    res = const * float(run["unresolved"])

    min = float("infinity")
    for people in run["peoples"]:
        if people["Count"] < min:
            min = people["Count"]

    sum_of_diff = 0
    for people in run["peoples"]:
        sum_of_diff += people["Count"] - min
    avg = sum_of_diff / len(run["peoples"])

    avg_diff = const * float(avg)
    return (3 * res) + avg_diff

if __name__ == '__main__':
    initializeDays()
    getConstraintsFromDrive()
    times = 0
    iterations = []
    maxUtil = float("infinity")
    #unresolved = -1
    bestRun = None
    for times in xrange(ITERATIONS_TIMES):
        global peoples
        peoples = copy.deepcopy(CONSTRAINTS)
        peoples = peoples["peoples"]
        index = 0
        placement = {}
        unresolvedCount = 0
        recursiveBackTracking(days[index], index)
        currRun = {"placements": copy.deepcopy(placement), "unresolved": copy.deepcopy(unresolvedCount), "peoples": peoples}
        utilValue = utility(currRun)
        #iterations.append({"placements
        #    placement), "unresolved": copy.deepcopy(unresolvedCount), "peoples": peoples})
        
        if utilValue < maxUtil:
            maxUtil = utilValue
            bestRun = currRun

        #unresolved = unresolvedCount
        print times

    #minUnResolved = len(days) + 1
    #bestRun = {}
    #for iteration in iterations:
    #    if iteration["unresolved"] < minUnResolved:
    #        minUnResolved = iteration["unresolved"]
    #        bestRun = copy.deepcopy(iteration)

    for day in days:
        print("" + str(day) + "  " + str(bestRun["placements"][day]))

    print("#######################")
    for people in bestRun["peoples"]:
        print(people["Name"] + ":" + str(people["Count"]))

    response = 'n'
    response = raw_input("commit? [y/n]")
    if response == 'y':
        sendInvite(bestRun)
        path = createCSV(bestRun)
        sendMesseage(bestRun,path)
