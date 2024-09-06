import os
from bs4 import BeautifulSoup
import lxml
import sys
import csv
import json
import pandas
import requests
import urllib.parse
from datetime import datetime

# Getting api_key from file to allow for hiding, changing or updating keys 
try:
    with open("api_key", "r") as file:
        api_key = file.read().strip()
except FileNotFoundError:
    print("Missing \"api_key\" file.")
    sys.exit(1)

def get_latlng_enc(addy):
  # Url encode address
  addy_enc = urllib.parse.quote(addy)
  # Geocode url
  geo_res = requests.get(f"https://maps.googleapis.com/maps/api/geocode/json?key={api_key}&address={addy_enc}")
  latlng = geo_res.json()["results"][0]["geometry"]["location"]
  lat = latlng["lat"]
  lng = latlng["lng"]
  location = f"{lat},{lng}"
  location_enc = urllib.parse.quote(location)  
  return location_enc


# Get all the internal links for a website. recursively
captured_urls = set() # Used with get_all_site_urls()
def get_all_site_urls(url, website_filter): # website_filter filters the domain name to prevent unrelated links
    if url in captured_urls:
        return     
    captured_urls.add(url) # adding the main url first
    try: # escape this website there are any issues
        res = requests.get(url)
    except Exception as err:
        print(f"Failed opening {url} due to {err}")
        # Remove this site from the list to avoid attempts to scrap in the next step
        # remove url from captured_urls
        captured_urls.remove(url)
        return

    soup = BeautifulSoup(res.content, 'lxml')
    # get all its child urls    
    child_urls = set()

    try:
        links = soup.find_all('a', href=True)
        for link in links:
            if link["href"].startswith("http") and website_filter in link["href"]: # Using a website filter restrict the urls to just those pertaining to the website
                #print(link["href"])
                child_urls.add(link["href"])
        # recursively capture
        for child_url in child_urls:
            get_all_site_urls(child_url, website_filter)
    except Exception as e:
            print("Error. Skipping. "+e)

# Get all the email addresses from a webpage
def get_all_email_addresses(website_pages):    
    emails = set()
    for link in website_pages:
        page_html = requests.get(link)
        content = page_html.content

        # Avoiding word documents
        content_type = page_html.headers.get('Content-Type', '').lower()
        # skip select content types
        if 'image/jpeg' in content_type:
            continue
        if not 'application/msword' in content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in content_type:
            soup = BeautifulSoup(content, "html.parser")
            # sticking to using mailto rather than regex to avoid scraping junk email addresses 
            try:            
                mailtos = soup.select('a[href^=mailto]')
                for mailto in mailtos:
                    print("in for mailto: "+ str(mailto.string))
                    if not str(mailto.string) == "None":
                        if "@" in mailto.string:
                            print("@ in mailto")
                            emails.add(mailto.string)
                            # Return a set of email addresses from this website
            except UnicodeDecodeError as e:
                print("Decoding error. Skipping. "+e)
        else:
            print("This is a word document. Skipped.")

    print(emails)
    return emails

    
def main(): 
    # Cycle through the results list of json objects 
    # in test.json to get the place_ids
    list_of_lead_data = []    
    

    # Use an api call to get the nearby places list
    # Geocode address inputs to use for location
    address = input("Address: ")
    keyword = urllib.parse.quote(input("Keyword: "))
    radius = input("Radius (meters): ")
    location= get_latlng_enc(address)
    tag = input("Tag(s) / Pipeline(s): ") 
    nearby_response = requests.get(f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?key={api_key}&location={location}&keyword={keyword}&radius={radius}")

    leads_couter = 0
    gmap_leads_results = nearby_response.json()["results"]
    # For each lead, get the place id to make a place_details call by id
    for lead in gmap_leads_results:
        print("\n*********START LEAD")
        leads_couter += 1
        lead_id = lead["place_id"]
        # Place details call using google's place_id
        lead_details = requests.get(f"https://maps.googleapis.com/maps/api/place/details/json?key={api_key}&place_id={lead_id}")
        if lead_details.status_code == 200:
            lead_details = lead_details.json()["result"]
            # Try to get email from website using beautiful soup
            emails = set()
            if "website" in lead_details:
                website_url = lead_details["website"]
                # Go fetch email                  
                # Get all links from this website while keepint the main set clean for other leads
                captured_urls.clear()
                # Creating a website filter to restrict the urls to just the website related urls
                website_filter = website_url # Using the home page url
                get_all_site_urls(website_url, website_filter)
                this_site_pages = captured_urls.copy()
                captured_urls.clear()
                
                # Get all emails from each link
                print("this site urls: "+str(this_site_pages))
                emails = get_all_email_addresses(this_site_pages)
                # Convert the emails set to a list                
                print("emails: " + str(emails))

                # TODO: Try to scrape contact name and position from site {website_url}
                contact_name = ""
                job_position = ""
                mobile_phone = ""
                
                #
                formatted_address = lead_details["formatted_address"] if "formatted_address" in lead_details else ""
              
                street_number, street, city, state, country, zip_code = ("",) * 6
                if "address_components" in lead_details:
                    for component in lead_details["address_components"]:
                        if "street_number" in component["types"]:
                            street_number = component["long_name"]
                        elif "route" in component["types"]:
                            street = component["long_name"]
                        elif "locality" in component["types"]:
                            city = component["long_name"]
                        elif "administrative_area_level_1" in component["types"]:
                            state = component["long_name"]                        
                        elif "country" in component["types"]:
                            country = component["long_name"]
                        elif "postal_code" in component["types"]:
                            zip_code = component["long_name"]

            lead = {
                "External ID": "g_place_id_" + str(lead_details["place_id"] if "place_id" in lead_details else ""),
                "Company Name": lead_details["name"] if "name" in lead_details else "",
                "Contact Name": contact_name,
                "Email": str(list(emails)).replace("[","").replace("]",""),
                "Job Position": job_position,
                "Phone": lead_details["formatted_phone_number"] if "formatted_phone_number" in lead_details else "",
                "Mobile": mobile_phone,
                "Street": street_number +" "+ street,
                "City": city,
                "State": state,
                "Zip": zip_code,
                "Country": country,
                "Formatted address": formatted_address,
                "Website": lead_details["website"] if "website" in lead_details else "",
                "Tags": tag
            }
            list_of_lead_data.append(lead)
            print("*********END LEAD")
    # Return a json file
    current_time = datetime.now()
    if not os.path.exists("leads"):
        os.makedirs("leads")
    file_name_formatter = "leads/leads_" + tag + "_" + current_time.strftime("%Y_%b_%d_%H%M%S")
    file_name = file_name_formatter+".json"
    with open(file_name, "w") as leads_file:
        json.dump(list_of_lead_data, leads_file, indent=4)

    # Return a csv file
    leads_json = json.dumps(list_of_lead_data)
    csv_str = pandas.read_json(leads_json)
    csv_str.to_csv(file_name_formatter + ".csv")
    print("Lead scrape completed. Total number of leads: "+ str(leads_couter))

    

if __name__ == '__main__':
    main()

