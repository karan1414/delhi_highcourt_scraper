import argparse
import re
import sys
from ast import parse
from datetime import date
from pprint import pprint

import openpyxl
import pandas as pd
import requests
from lxml import html

dhc_case_page = '/case.asp'
dhc_case_details = '/dhc_case_status_list_new.asp'
dhc_base_url = 'https://delhihighcourt.nic.in'

session = requests.Session()

parser = argparse.ArgumentParser()
parser.add_argument('--year', type=float, default=2021, help='Year For which cases data is to be shown')
args = parser.parse_args()

xpath_for_years_dropdown = '//select[@id="c_year"]/option'
xpath_for_hidden_input_digit = '//input[@id="hiddeninputdigit"]'
xpath_for_list_of_cases = '//ul[@class="clearfix grid"]/li'
xpath_for_list_of_case_numbers = '(//ul[@class="clearfix grid"]/li/span[@class="pull-left width-33 title al"])'
xpath_for_case_status = '(//ul[@class="clearfix grid"]/li/span[@class="pull-left width-33 title al"])/font'
xpath_for_petitioners = '//ul[@class="clearfix grid"]/li/span[@class="pull-left width-30 title al"]/text()[1]'
xpath_for_respondents = '//ul[@class="clearfix grid"]/li/span[@class="pull-left width-30 title al"]/text()[2]'
xpath_for_advocates = '//ul[@class="clearfix grid"]/li/span[@class="pull-left width-30 title al"]/text()[3]'
xpath_for_court_numbers = '//ul[@class="clearfix grid"]/li/span[@class="pull-left width-30 title al last"]/text()[1]'
xpath_for_listing_dates = '//ul[@class="clearfix grid"]/li/span[@class="pull-left width-30 title al last"]/text()[2]'

respondent_substitution_regex = r'Vs\.?'
court_number_regex = r'\s*Court\s*No\.?\s*\:?\s*(\d+)'
next_date_regex = r'Next\s*Date\:?\s*(\d{2}\/\d{2}\/\d{4})'
advocate_regex = r'\s*Advocate\s*:?\s*([a-zA-Z\s*]+)'

def parse_dhc_case_details_page(page_html_content):
    data_rows = page_html_content.xpath(xpath_for_list_of_cases)
    case_nums = page_html_content.xpath(xpath_for_list_of_case_numbers)
    case_status_arr = page_html_content.xpath(xpath_for_case_status)
    pet_arr = page_html_content.xpath(xpath_for_petitioners)
    res_arr = page_html_content.xpath(xpath_for_respondents)
    adv_arr = page_html_content.xpath(xpath_for_advocates)
    court_num_arr = page_html_content.xpath(xpath_for_court_numbers)
    listing_date_arr = page_html_content.xpath(xpath_for_listing_dates)

    cases_data_arr = []
    for i in range(0, len(data_rows)):
        case_doc = {}
        if not len(case_nums):
            print("Case-number-not-found")
            continue
        case_doc['case_num'] = case_nums[i].text.strip()
        case_doc['case_status'] = case_status_arr[i].text.strip("[]").strip()

        # petitioner respondent data
        case_doc['petitioner'] = pet_arr[i].strip() if len(pet_arr) and pet_arr[i] else "N/A"
        respondent = res_arr[i].strip() if len(pet_arr) and pet_arr[i] else "N/A"
        case_doc['respondent'] = re.sub(respondent_substitution_regex,'',respondent, re.I).strip()
        
        # listing data
        case_doc['listing_date'] = listing_date_arr[i].strip() if len(listing_date_arr) and listing_date_arr[i] else ''
        
        # court number / next date data
        court_num = court_num_arr[i].strip() if len(court_num_arr) and court_num_arr[i] else 'N/A'
        
        court_num_exists = re.search(court_number_regex, court_num, re.I)
        if court_num_exists:
            case_doc['court_num'] = court_num_exists.group(1).strip()
        
        next_date_exists = re.search(next_date_regex, court_num, re.I)
        if next_date_exists: 
            case_doc['next_date'] = next_date_exists.group(1).strip()
            case_doc['court_num'] = 'N/A'
        
        # advocate data
        adv_exists = re.search(advocate_regex, adv_arr[i])
        if adv_exists:
            case_doc['advocate'] = adv_exists.group(1).strip()

        cases_data_arr.append(case_doc)
    return cases_data_arr

def get_dhc_data(year):
    # get homepage
    dhc_homepage_resp = session.get(dhc_base_url, verify=False)
    if not dhc_homepage_resp:
        print('Error-while-fetching-delhi-highcourt-homepage')

    # get case / listing page
    dhc_case_page_url = dhc_base_url + dhc_case_page
    dhc_case_page_resp = session.get(dhc_case_page_url)
    if not dhc_case_page_resp:
        print('Error-while-fetching-delhi-highcourt-case/filing-page')
    dhc_case_page_content = html.fromstring(dhc_case_page_resp.content)

    # get years from year dropdown
    options_arr = dhc_case_page_content.xpath(xpath_for_years_dropdown)
    if not options_arr:
        print("could-not-find-dropdown-of-years")

    years_arr = [option.attrib['value'] for option in options_arr]
    if str(year) not in years_arr:
        print('cannot-find-required-year')

    # get the random number that is generate and needs to be entered
    
    hidden_input_int = dhc_case_page_content.xpath(xpath_for_hidden_input_digit)
    if not hidden_input_int or not hidden_input_int[0].attrib['value']:
        print('Cannot-find-random-integer-value')
    
    payload = {
        "sno": "1",
        "ctype_29": "ARB. A. (COMM.)",
        "cno": "",
        "cyear": year,
        "input": hidden_input_int,
        "hidden_input_int": hidden_input_int
    }

    # get case list page
    dhc_case_details_url = dhc_base_url + dhc_case_details
    dhc_case_details_result = session.post(dhc_case_details_url, data=payload, verify=False)

    if dhc_case_details_result.status_code != 200 or not dhc_case_details_result:
        print("unable-to-find-dhc-case-details-page")

    dhc_case_details_page_content = html.fromstring(dhc_case_details_result.content)
    parsed_details = parse_dhc_case_details_page(page_html_content=dhc_case_details_page_content)

    if not parsed_details:
        print('Unable-to-parse-details-page-and-get-data')

    df = pd.DataFrame.from_dict(parsed_details, orient='columns')
    df.to_excel('Case_details.xlsx')

if __name__ == '__main__':
    current_day = date.today()
    current_year = current_day.year

    if int(args.year) > current_year:
        print("Please-select-valid-year")
    
    dhc_data = get_dhc_data(year=args.year)
