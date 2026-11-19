"""#119: build the on-time field, the report "On Time by Month", item 18's column and D5's chart from before/.

Text edits, each with an assert. Never prints XML: D5's filter values are staff names.
Usage: python3 -I make_build.py <topic folder holding before/>
"""
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(sys.argv[1]).resolve()
SRC = HERE / 'before'
OUT = HERE / 'build'
DST = OUT / 'force-app' / 'main' / 'default'
REPORTS = 'reports/GLOW_Monthly_Reports'
DASH = 'dashboards/GLOW_Monthly_Dashboards/DGdiHNHQWRoBNviGBlNWJPnSYqTlMR.dashboard-meta.xml'
ITEM18 = 'Reports_completed_on_time_hOZ'
APPROVAL = 'Approval_Status_by_Month'
NEW = 'On_Time_by_Month'
FIELD = 'Submitted_On_Time__c'
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'


def sub_once(text, old, new, what):
    n = text.count(old)
    assert n == 1, f'{what}: expected 1 match, found {n}'
    return text.replace(old, new)


def write(rel, text):
    p = DST / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
(OUT / 'sfdx-project.json').write_text((HERE / 'sfdx-project.json').read_text())

# the submission date is a Date formula (CreatedDate, its GMT date), Period__c a Date formula, always the 1st:
# the deadline ADDMONTHS(Period__c, 1) + 14 is the 15th of the month after (December -> 15 January)
sub = (SRC / 'objects/DHIS2__c/fields/Monthly_Report_submission_date__c.field-meta.xml').read_text()
assert '<type>Date</type>' in sub and '<formula>CreatedDate</formula>' in sub, 'submission date is no Date formula'
per = (SRC / 'objects/DHIS2__c/fields/Period__c.field-meta.xml').read_text()
assert '<type>Date</type>' in per and re.search(r',\s*1\s*\)\s*\)\s*</formula>', per), 'Period__c is not the 1st'
write(f'objects/DHIS2__c/fields/{FIELD}.field-meta.xml', HEAD + f"""<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>{FIELD}</fullName>
    <description>On time when Monthly_Report_submission_date__c is on or before the 15th of the month after Period__c (December: 15 January), otherwise Late; blank when either date is blank. The rule: Ryan and GLOW, 2026-11-02 (DECISIONS 2026-11-20). Ticket #119.</description>
    <externalId>false</externalId>
    <formula>IF(
  OR(ISBLANK(Period__c), ISBLANK(Monthly_Report_submission_date__c)),
  &quot;&quot;,
  IF(Monthly_Report_submission_date__c &lt;= ADDMONTHS(Period__c, 1) + 14, &quot;On time&quot;, &quot;Late&quot;)
)</formula>
    <formulaTreatBlanksAs>BlankAsBlank</formulaTreatBlanksAs>
    <inlineHelpText>On time when submitted on or before the 15th of the month after the report&apos;s month.</inlineHelpText>
    <label>Submitted On Time</label>
    <required>false</required>
    <trackTrending>false</trackTrending>
    <type>Text</type>
    <unique>false</unique>
</CustomField>
""")

# the report type: the column after the submission date, not checked by default
rt = (SRC / 'reportTypes/Dhis2.reportType-meta.xml').read_text()
m = re.search(r' *<columns>\s*<checkedByDefault>\w+</checkedByDefault>\s*<field>Monthly_Report_submission_date__c</field>'
              r'\s*<table>DHIS2__c</table>\s*</columns>\n', rt)
assert m and FIELD not in rt, 'report type anchor'
col = re.sub(r'<checkedByDefault>\w+<', '<checkedByDefault>false<',
             m.group(0).replace('Monthly_Report_submission_date__c', FIELD))
write('reportTypes/Dhis2.reportType-meta.xml', rt[:m.end()] + col + rt[m.end():])

# read access only, for the profiles that read Period__c and the submission date (as #195)
for prof in ('Admin', 'GLOW Standard User'):
    src = (SRC / f'profiles/{prof}.profile-meta.xml').read_text()
    for f in ('Period__c', 'Monthly_Report_submission_date__c'):
        assert re.search(r'<editable>false</editable>\s*<field>DHIS2__c\.' + f + r'</field>\s*<readable>true</readable>',
                         src), f'{prof} does not read {f}'
    write(f'profiles/{prof}.profile-meta.xml',
          HEAD + '<Profile xmlns="http://soap.sforce.com/2006/04/metadata">\n    <fieldPermissions>\n'
          f'        <editable>false</editable>\n        <field>DHIS2__c.{FIELD}</field>\n'
          '        <readable>true</readable>\n    </fieldPermissions>\n</Profile>\n')

# item 18: the field as a column after the submission date; groupings, filters and label unchanged
t18 = (SRC / f'{REPORTS}/{ITEM18}.report-meta.xml').read_text()
anchor = '    <columns>\n        <field>DHIS2__c$Monthly_Report_submission_date__c</field>\n    </columns>\n'
t18 = sub_once(t18, anchor, anchor + f'    <columns>\n        <field>DHIS2__c${FIELD}</field>\n    </columns>\n', 'item 18')
assert '<name>Reports completed on time</name>' in t18
write(f'{REPORTS}/{ITEM18}.report-meta.xml', t18)

# the new report: the live "Approval Status by Month" (its filters as they are today), grouped by the field
ta = (SRC / f'{REPORTS}/{APPROVAL}.report-meta.xml').read_text()
tn = sub_once(ta, '<name>Approval Status by Month</name>', '<name>On Time by Month</name>', 'name')
tn, n = re.subn(r'<description>.*?</description>',
                '<description>Monthly Reports submitted on time and late, by month, the reporting year (#119)</description>', tn)
assert n == 1, 'description'
tn = sub_once(tn, '<field>DHIS2__c$Approved__c</field>', f'<field>DHIS2__c${FIELD}</field>', 'grouping')
assert 'Approved__c' not in tn and tn.count('<groupingsDown>') == 2
write(f'{REPORTS}/{NEW}.report-meta.xml', tn)

# D5: a stacked column on the new report, full width below the approval overview, both dashboard filters
d5 = (SRC / DASH).read_text()
comps = re.findall(r' *<dashboardGridComponents>\n.*?</dashboardGridComponents>\n', d5, re.S)
assert len(comps) == 3, f'D5 has {len(comps)} components'
ov = comps[2]
assert '<report>GLOW_Monthly_Reports/Approval_Status_by_Month</report>' in ov and '<rowIndex>10</rowIndex>' in ov
assert '<rowSpan>8</rowSpan>' in ov and '<colSpan>12</colSpan>' in ov and ov.count('<dashboardFilterColumns>') == 2
c = sub_once(ov, '<report>GLOW_Monthly_Reports/Approval_Status_by_Month</report>',
             f'<report>GLOW_Monthly_Reports/{NEW}</report>', 'c report')
c = sub_once(c, '<groupingColumn>DHIS2__c$Approved__c</groupingColumn>',
             f'<groupingColumn>DHIS2__c${FIELD}</groupingColumn>', 'c grouping')
c, n = re.subn(r'<header>.*?</header>', '<header>Monthly Reports Submitted On Time vs Late by Month</header>', c)
assert n == 1, 'c header'
c = sub_once(c, '<rowIndex>10</rowIndex>', '<rowIndex>18</rowIndex>', 'c row')
d5 = sub_once(d5, ov, ov + c, 'd5')
write(DASH, d5)

(OUT / 'package.xml').write_text(HEAD + """<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types><members>DHIS2__c.Submitted_On_Time__c</members><name>CustomField</name></types>
    <types><members>Dhis2</members><name>ReportType</name></types>
    <types><members>Admin</members><members>GLOW Standard User</members><name>Profile</name></types>
    <types><members>GLOW_Monthly_Reports/Reports_completed_on_time_hOZ</members><members>GLOW_Monthly_Reports/On_Time_by_Month</members><name>Report</name></types>
    <types><members>GLOW_Monthly_Dashboards/DGdiHNHQWRoBNviGBlNWJPnSYqTlMR</members><name>Dashboard</name></types>
    <version>67.0</version>
</Package>
""")
print('built', sum(1 for x in DST.rglob('*') if x.is_file()), 'files')
