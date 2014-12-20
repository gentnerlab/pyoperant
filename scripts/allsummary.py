#!/usr/bin/env python
import re
import datetime as dt
from glab_common.utils import load_data_pandas
from socket import gethostname
import warnings
from pyoperant.local import DATA_PATH

process_fname = DATA_PATH + "panel_subject_behavior"

box_nums = []
bird_nums = []
processes = []

with open(process_fname, 'rt') as in_f:
    for line in in_f.readlines():
        if line.startswith('#') or not line.strip():
            pass # skip comment lines & blank lines
        else:
            spl_line = line.split()
            if spl_line[1] == "1": #box enabled
                box_nums.append(int(spl_line[0]))
                bird_nums.append(int(spl_line[2]))
                processes.append(spl_line[-1])

subjects = ['B%d' % (bird_num) for bird_num in bird_nums]
# load all data
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    behav_data = load_data_pandas(subjects, DATA_PATH);

with open(DATA_PATH+'all.summary','w') as f:

    f.write("this all.summary generated at %s\n" % (dt.datetime.now().strftime('%x %X')))

    f.write("FeedErr(won't come up, won't go down, already up, resp during feed)\n")

    # Now loop through each bird and grab the error info from each summaryDAT file
    for (box, bird, proc) in zip(box_nums, bird_nums, processes):
        try:
            if proc in ('Lights',):
                f.write("box %d\tB%d\t %s\n" % (box, bird, proc))
            else:
                summaryfname = "/home/bird/opdat/B%d/%d.summaryDAT" % (bird, bird)
                with open(summaryfname, 'rt') as sdat:
                    sdata = sdat.read()

                m = re.search(r"failures today: (\w+)", sdata)
                hopper_failures = m.group(1)
                m = re.search(r"down failures today: (\w+)", sdata)
                godown_failures = m.group(1)
                m = re.search(r"up failures today: (\w+)", sdata)
                goup_failures = m.group(1)
                m = re.search(r"Responses during feed: (\w+)", sdata)
                resp_feed = m.group(1)

                subj = 'B%d' % (bird)
                df = behav_data[subj]
                todays_data = df[(df.index.date-dt.datetime.today().date()) == dt.timedelta(days=0)]
                feeder_ops = sum(todays_data['reward'].values)
                trials_run = len(todays_data)
                noRs = sum(todays_data['response'].values=='none')
                TOs = trials_run-feeder_ops-noRs
                last_trial_time = todays_data.sort().tail().index[-1]
                if last_trial_time.day != dt.datetime.now().day:
                    datediff = '(not today)'
                else:
                    minutes_ago = (dt.datetime.now() - last_trial_time).seconds / 60
                    datediff = '(%d mins ago)' % (minutes_ago)
                
                outline = "box %d\tB%d\t %s  \ttrls=%s  \tfeeds=%d  \tTOs=%d  \tnoRs=%d  \tFeedErrs=(%s,%s,%s,%s)  \tlast @ %s %s\n" % (box, bird, proc, trials_run, feeder_ops, TOs, noRs, 
                  hopper_failures, godown_failures, goup_failures, resp_feed, last_trial_time.strftime('%x %X'), datediff)
                f.write(outline)
        except Exception as e:
            f.write("box %d\tB%d\t Error opening SummaryDat or incorrect format\n" % (box, bird))