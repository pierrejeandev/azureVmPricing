#!/usr/bin/python3

import requests
import json
import datetime
import re
import os

print('###############################################################################')
print('###############################################################################')

outputFolder = 'Data' + os.path.sep


with open('AzureVMData.js') as vmsDataFile:
    vmsData = json.load(vmsDataFile)


priceData = {}

for vmid, vmData in vmsData['offers'].items():
    if 'prices' in vmData:
        for region, prices in vmData['prices'].items():
            if not region in priceData:
                priceData[region] = {}
            priceData[region][vmid] = prices
        vmData.pop('prices')
    # if 'baseOfferSlug' in vmData:
    #     print(vmid + ':' + vmData['baseOfferSlug'])
    # else:
    #     print(vmid )  

vmsData['refRegionPricesFiles'] = {}

for region, rData in priceData.items():
    regionFilename = outputFolder + 'AzureVMPrices_' + region + '.js'
    vmsData['refRegionPricesFiles'][region] = regionFilename
    with open(regionFilename, 'w') as outfile:
        json.dump(rData, outfile, indent = 1, sort_keys = True) 


# vrite vmsData withoutPrices
with open(outputFolder + 'AzureVMDataWOPrices.js', 'w') as outfile:
    json.dump(vmsData, outfile, indent = 1, sort_keys = True)


# print('###############################################################################')
# ### Debug offers lists and slug
# vmsData = { 'currencyData': {}, 'offers': {}, 
#   'refDatacenter': [], 'refOffers': [], 'refCores': [], 'refRam': [], 
#   'sources': { 'docs': {}, 'prices': {} }, 'updateDateUtc': datetime.datetime.utcnow().isoformat() }

# def getOfferFromPricing (url, vmsData, priceSource):
#     r = requests.get(url)
#     data = r.json()
#     vmsData['sources']['prices'][priceSource] = url
#     offers = vmsData['offers']
#     refDatacenter = vmsData['refDatacenter']
#     refOffers = vmsData['refOffers']
#     for offer in data['offers']:

#         # if offer == "transactions":
#         #     continue

#         o = data['offers'][offer]
#         parts = offer.split("-")
#         index = 2
#         if len(parts) >= 5 and ( parts[-2] == 'v2' or parts[-2] == 'v3' ):
#             # examples : windows-ds11-1-v2-standard ; rhel-sap-hana-ha-ds11-1-v2-standard ; ubuntu-advantage-advanced-e4-2s-v3-standard
#             index = 4
#         elif len(parts) >= 4 and re.match(r'^\d+(ms)?$', parts[-2]):
#             # examples : windows-m16ms-standard : rhel-sap-hana-ha-m16ms-standard ; sql-standard-m64-16ms-standard
#             index = 3
#         offerid = "-".join(parts[0:-index])
#         vmsize = "-".join(parts[-index:-1]).capitalize()
#         tier = parts[-1].capitalize()
#         slug = ''
#         if 'baseOfferSlug' in o:
#             slug = o['baseOfferSlug']

#         # print(priceSource + '\t' + offer + '\t' + offerid + '\t' + slug + '\t' + str(index))
#         print(priceSource + '\t' + str(index) + '\t' + offer + '\t' + offerid + '\t' + vmsize + '\t' + tier)

# getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-software/calculator/?culture=en-us&discount=mosp', vmsData, 'software')
# getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-ahb/calculator/?culture=en-us&discount=mosp', vmsData, 'ahb')
# getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-base/calculator/?culture=en-us&discount=mosp', vmsData, 'base')
