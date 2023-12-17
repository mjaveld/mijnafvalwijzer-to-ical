#!/usr/bin/env python

import sys
import re
import requests
import argparse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, Alarm, vDuration, vDatetime

#Constants
GITHUB_URL = "https://github.com/vwout/mijnafvalwijzer-to-ical"

MONTHS = {
  "januari":   1,
  "februari":  2,
  "maart":     3,
  "april":     4,
  "mei":       5,
  "juni":      6,
  "juli":      7,
  "augustus":  8,
  "september": 9,
  "oktober":   10,
  "november":  11,
  "december":  12
}

DEFAULT_ALARM_CUSTOM_UNSET = -1
DEFAULT_ALARM_TIME_TIMEDELTA = timedelta(hours=8,minutes=0)

ALLOWED_WASTE_TYPES_ALL_CHAR = '*'
allowed_waste_types = {
  "gft": DEFAULT_ALARM_CUSTOM_UNSET,
  "glas": DEFAULT_ALARM_CUSTOM_UNSET,
  "kca": DEFAULT_ALARM_CUSTOM_UNSET,
  "papier": DEFAULT_ALARM_CUSTOM_UNSET,
  "pd": DEFAULT_ALARM_CUSTOM_UNSET,
  "pmd": DEFAULT_ALARM_CUSTOM_UNSET,
  "textiel": DEFAULT_ALARM_CUSTOM_UNSET,
  "grofvuil": DEFAULT_ALARM_CUSTOM_UNSET,
  "restafval": DEFAULT_ALARM_CUSTOM_UNSET
}

#Setup parsing of commandline args
parser = argparse.ArgumentParser(description="Get iCal (.ics) from Afvalwijzer",
  epilog="Also check the github for more information: {}".format(GITHUB_URL))
parser.add_argument("postal_code", help="format: 1234AA")
parser.add_argument("housenumber", help="format: 0000AA")

waste_types_helptext = """{}.
Select which waste types you want. '{}' selects them all.
Multiple choices allowed, seperated by ','.
Example: 'gft,papier,restafval'
""".format([ALLOWED_WASTE_TYPES_ALL_CHAR, *allowed_waste_types], ALLOWED_WASTE_TYPES_ALL_CHAR)
parser.add_argument("waste_types", help=waste_types_helptext)

alarm_arg_name = "--alarm"
alarm_arg_metavar = "CUSTOM_ALARM"
alarm_custom_helptext = """[{}] Allows custom schedule for alarms/notifications. 
Format: '[waste_type]:[-]0359,[waste_type]:[-][0359]'. 
[waste_type] should be equal to the waste_type argument.
[-] can be supplied to set it on the day before instead of the same day.
[0359] is a 24hr time setting relative to [-].
""".format(alarm_arg_metavar)
alarm_helptext = """Adds Alarms/Notifications on the calendar items. 
Defaults to **ADD DYNAMIC SETTING**.
{}
""".format(alarm_custom_helptext)
parser.add_argument(alarm_arg_name, metavar=alarm_arg_metavar, nargs="?", const=True, help=alarm_helptext)

args = parser.parse_args()

#Process arguments into values used
postal_code = args.postal_code

housenumber = args.housenumber
housenumber_suffix = ""
housenumber_re = re.search(r"^(\d+)(\D*)$", housenumber)
if housenumber_re:
  housenumber = housenumber_re.group(1)
  housenumber_suffix = housenumber_re.group(2) or ""

if args.waste_types == ALLOWED_WASTE_TYPES_ALL_CHAR:
  waste_types = allowed_waste_types
else:
  waste_types = args.waste_types.split(',')

alarm_enabled = False
alarms_custom = []
if isinstance(args.alarm, str):
  alarms_custom = args.alarm.replace(':', ',').split(',')
  alarm_enabled = True
elif args.alarm:
  alarm_enabled = True

if len(alarms_custom) % 2:
  print("{} [{}] format is not correct.".format(alarm_arg_name, alarm_arg_metavar))
  parser.print_help()
  parser.exit()

if alarm_enabled and alarms_custom:
  i = 0
  while i < len(alarms_custom):
    waste = alarms_custom[i]
    time = alarms_custom[i + 1]
    delta_day = 0
    if time.startswith('-'):
      delta_day = -1
      time = time[1:]
    delta_hour = int(time[0:2])
    delta_minutes = int(time[2:])
    allowed_waste_types[waste] = timedelta(delta_day, hours=delta_hour, minutes=delta_minutes)
    i += 2
elif alarm_enabled:
  for waste in allowed_waste_types:
    allowed_waste_types[waste] = DEFAULT_ALARM_TIME_TIMEDELTA

#Request and parse html
url = "https://www.mijnafvalwijzer.nl/nl/{0}/{1}/{2}".format(postal_code, housenumber, housenumber_suffix)
aw_html = requests.get(url)
aw = BeautifulSoup(aw_html.text, "html.parser")

#Create calendar object for ics file
cal = Calendar()
cal.add("prodid", "-//{0}//NL".format(GITHUB_URL))
cal.add("version", "2.0")
cal.add("name", "Afvalkalender")
cal.add("x-wr-calname", "Afvalkalender")
cal.add("x-wr-timezone", "Europe/Amsterdam")
cal.add("description", aw.title.string)
cal.add("url", url)

#Process all anchor-tags containing waste collection days
now = datetime.now()
for anchor in aw.find_all("a", "wasteInfoIcon textDecorationNone"):
    # Get the waste type from the fragment in the anchors href
    waste_type = anchor["href"].replace("#", "").replace("waste-", "")
    if waste_type == "" or waste_type == "javascript:void(0);":
      if anchor.p.has_attr("class"):
        waste_type = anchor.p["class"][0]

    if waste_type in waste_types:
      anchor_text = re.search(r"(\w+) (\d+) (\w+)( (\d+))?", anchor.p.text)
      item_date = datetime(int(anchor_text.group(5) or now.year), MONTHS.get(anchor_text.group(3), 0), int(anchor_text.group(2)))
      item_descr = anchor.find("span", {"class": "afvaldescr"}).text.replace(r"\,", ",")
      item_summary = "Afval - {0}".format(item_descr)

      event = Event()
      event.add("uid", "{0}-{1}-{2}".format(item_date.timetuple().tm_year, item_date.timetuple().tm_yday, waste_type))
      event.add("dtstamp", now)
      # event.add("dtstart", item_date)
      event.add("dtstart", vDatetime(item_date))
      event.add("dtend", vDatetime(item_date + timedelta(1)))
      event.add("summary", item_summary)
      event.add("description", item_descr)
      event.add("TRANSP", "TRANSPARENT")

      alarm_custom_time = allowed_waste_types[waste_type]
      if alarm_enabled and alarm_custom_time is not DEFAULT_ALARM_CUSTOM_UNSET:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("trigger", value=vDuration(alarm_custom_time))
        alarm.add("description", item_summary)
        event.add_component(alarm)
      
      cal.add_component(event)

#Print to stdout, can pipe out to file
print(cal.to_ical().decode("utf-8"), file=open("testing.ics", "w+t"))
# print(cal.to_ical().decode("utf-8"))
