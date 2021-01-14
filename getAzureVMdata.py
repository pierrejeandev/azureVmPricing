#!/usr/bin/python3

import requests
import re
from pprint import pprint,pformat
import json
import datetime

def getOfferFromPricing (url, vmsData, priceSource):
    r = requests.get(url)
    data = r.json()
    vmsData['sources']['prices'][priceSource] = url
    offers = vmsData['offers']
    refDatacenter = vmsData['refDatacenter']
    refOffers = vmsData['refOffers']
    for offer in data['offers']:

        if offer == "transactions":
            continue

        o = data['offers'][offer]

        # extract data from the offer id
        # examples : windows-d15iv2-standard ; rhel-sap-business-applications-d15v2-standard ; linux-m64-standard
        parts = offer.split("-")
        index = 2
        if len(parts) >= 5 and ( parts[-2] == 'v2' or parts[-2] == 'v3' ):
            # examples : windows-ds11-1-v2-standard ; rhel-sap-hana-ha-ds11-1-v2-standard ; ubuntu-advantage-advanced-e4-2s-v3-standard
            index = 4
        elif len(parts) >= 4 and re.match(r'^\d+(ms)?$', parts[-2]):
            # examples : windows-m16ms-standard : rhel-sap-hana-ha-m16ms-standard ; sql-standard-m64-16ms-standard
            index = 3
        offerid = "-".join(parts[0:-index])
        o['vmsize'] = "-".join(parts[-index:-1]).capitalize()
        o['tier'] = parts[-1].capitalize()

        # add offer to refOffer
        if not offerid in refOffers:
            refOffers.append(offerid)

        # get prices for VM Tier/Size
        vmid = o['tier'] + "_" + o['vmsize']
        prices = {}
        for datacenter in o['prices']:
            if not datacenter in refDatacenter:
                refDatacenter.append(datacenter)
            prices[datacenter] = {}
            prices[datacenter][offerid] = o['prices'][datacenter]['value']
        o['prices'] = prices

        if vmid in offers:
            # push series value
            if 'series' in o and not 'series' in offers[vmid]:
                offers[vmid]['series'] = o['series']
            # merge prices
            for datacenter in o['prices']:
                if not datacenter in offers[vmid]['prices']:
                    offers[vmid]['prices'][datacenter] = {}
                for poffer in prices[datacenter]:
                    offers[vmid]['prices'][datacenter][poffer] = prices[datacenter][poffer]
        else:
            offers[vmid] = o

        o = 0
        # if 'europe-north' in o['prices']:
        #     o['price-europe-north'] = o['prices']['europe-north']['value']
        # if 'europe-west' in o['prices']:
        #     o['price-europe-west'] = o['prices']['europe-west']['value']
        # o.pop('prices', None)

    # end for offer in data['offers']:
# end def getOfferFromPricing (url, offers)


print('Loading currency ...')
url = 'https://azure.microsoft.com/en-us/pricing/calculator/'
r = requests.get(url)

vmsData = { 'currencyData': {}, 'offers': {}, 
  'refDatacenter': [], 'refOffers': [], 'refCores': [], 'refRam': [], 
  'sources': { 'docs': {}, 'prices': {} }, 'updateDateUtc': datetime.datetime.utcnow().isoformat() }

for line in r.iter_lines():
    line = line.decode("utf-8") 
    line = line.strip()
    if line.startswith('global.rawCurrencyData = '):
        line = line.replace('global.rawCurrencyData = ', '')
        line = line[0:-1]  # remove trailing ';'
        vmsData['currencyData'] = json.loads(line)
        break

print('Loading VM pricing...')

getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-software/calculator/?culture=en-us&discount=mosp', vmsData, 'software')
getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-ahb/calculator/?culture=en-us&discount=mosp', vmsData, 'ahb')
getOfferFromPricing('https://azure.microsoft.com/api/v2/pricing/virtual-machines-base/calculator/?culture=en-us&discount=mosp', vmsData, 'base')

#pprint(offers)

def getVmSpecFromWebPage(url, vmsData, rows, source):
    vmsData['sources']['docs'][source] = url
    r = requests.get(url)
    if r.status_code  != 200:
        raise Exception("Failed to get url " + url + ", HTTP Code: " + str(r.status_code) )
    inTable = False
    inHeader = False
    columns = {}
    row = {}
    # rows = []
    columnsIndex = 0
    series = ''
    processor = ''

    for line in r.iter_lines():
        line = line.decode("utf-8") 
        if (not inTable) and line.startswith('<thead>'):
            # begin of table headers
            inTable = True
            inHeader = True
            columns = {}
        elif inHeader and line.startswith('<th>'):
            # header
            m = re.search('<th>(.*)</th>', line)
            columns[columnsIndex] = m.group(1)
            columnsIndex += 1
        elif inHeader and line.startswith('</thead>'):
            # end of headers
            inHeader = False
        elif inTable and line.startswith('<tr>'):
            # new row
            row = { 'source': source }
            if series != '':
                if series == 'DS':
                    series = 'Ds'
                row['series'] = series
            if processor != '' and not 'Processor' in row:
                row['Processor'] = processor
            columnsIndex = 0
        elif inTable and (not inHeader) and line.startswith('</tr>'):
            # end of row -> append VM
            rows.append(row)
        elif inTable and line.startswith('<td>'):
            # value (table cell)
            m = re.search('<td>([^<]*)(\\s?<.*)?</td>', line)
            row[columns[columnsIndex]] = m.group(1).replace("&nbsp;", "").strip()
            columnsIndex += 1
        elif inTable and line.startswith('</table>'):
            # end of table
            inTable = False
            series = ''
            processor = ''
        elif line.startswith('<h2 id=') or line.startswith('<h3 id='): 
            # examples:
            # <h2 id="ev3-series">Ev3-series</h2>  
            # <h2 id="dsv2-series-11-15">DSv2-series 11-15<a class="docon docon-link heading-anchor" href="#dsv2-series-11-15" aria-labelledby="dsv2-series-11-15"></a></h2>
            # <h2 id="nvv4-series-preview--1">NVv4-series (Preview)  <sup>1</sup><a class="docon docon-link heading-anchor" href="#nvv4-series-preview--1" aria-labelledby="nvv4-series-preview--1"></a></h2>
            # <h3 id="basic-a">Basic A</h3>
            # <h3 id="a-series">A-series</h3>
            # <h3 id="a-series---compute-intensive-instances">A-series - compute-intensive instances</h3>
            # <h3 id="d-series">D-series</h3>
            
            processor = ''
            series = ''
            m = re.search(r'<h[23] id="\w+-series[\w-]*">(\w+)-series.*</h[23]>', line)
            if m:
                series = m.group(1)
            elif line.startswith('<h3 id="basic-a">Basic A</h3>'):
                series = 'A'
        elif 'Intel Xeon' in line or 'Intel® Xeon®' in line or 'AMD' in line:
            # examples
            # feature the Intel® Xeon® 8171M 2.1 GHz (Skylake) or the Intel® Xeon® E5-2673 v4 2.3 GHz (Broadwell) processors
            # powered by Intel Xeon E5-2690 v3 (Haswell) CPUs
            # feature 44 Intel Xeon Platinum 8168 processor
            # the Intel Xeon E5-2690 v3 (Haswell) processor
            # running on the <a href="https://www.amd.com/en/products/epyc-7000-series" data-linktype="external">AMD EPYC ™ 7551 processor</a> with 
            # feature 120 AMD EPYC 7742 processor
            # feature 8 or 16 Intel Xeon E5 2667 v3 processor 
            # utilize AMD’s 2.35Ghz EPYC<sup>TM</sup> 7452 processor 
            # utilize AMD’s 2.35Ghz EPYC<sup>TM</sup> 7452 processor 
            # based on the Intel(R) Xeon(R) CPU E7-8890 v3 @ 2.50GHz
            line = line.replace('<sup>TM</sup>', '').replace('®', '').replace('(R)', '')
            parts = re.split(r', | or ', line)
            processor = ''
            for part in parts:
                m = re.search(r'Intel Xeon( CPU)?\s(.{7,15})\s(\(|processor|\d\.\d+\s?G[Hh]z)', part)
                if m:
                    processor += 'Xeon ' + re.sub(r'\s@$', '', re.sub(r'\s\d\.\d+\s?G[hH]z', '', m.group(2))) + ', '
                m = re.search(r'(AMD|AMD’s( \d\.\d+G[hH]z)?)\s(.{7,15})\s(\(|processor|\d\.\d+\s?G[Hh]z)', part)
                if m:
                    processor += 'AMD ' + re.sub(r'\s\d\.\d+\s?G[hH]z', '', m.group(3)) + ', '
            if len(processor) > 2:
                processor = processor[:-2]
            # print ('PROCESSOR line: ' + line)
            # print ('PROCESSOR found: ' + processor)

    # end for line in r.iter_lines():

    return rows
# end def getVmSpecFromWebPage(url, rows):

def parseIops(iops):
    if iops.find('x') != -1:
        parts = iops.split('x', 1)
        iops = int(parts[0]) * int(parts[1])
    else:
        iops = int(iops)
    return iops
# end def parseIops(iops)

print('Loading VM specs...')
rawdata = []

# getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/test',                  vmsData, rawdata, 'test')

# getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-general', vmsData, rawdata, 'general')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/av2-series',                  vmsData, rawdata, 'general-av2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/sizes-b-series-burstable',    vmsData, rawdata, 'general-b')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dcv2-series',                 vmsData, rawdata, 'general-dcv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dv2-dsv2-series',             vmsData, rawdata, 'general-dv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dv3-dsv3-series',             vmsData, rawdata, 'general-dv3')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dav4-dasv4-series',           vmsData, rawdata, 'general-dav4')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ddv4-ddsv4-series',           vmsData, rawdata, 'general-ddv4')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dv4-dsv4-series',             vmsData, rawdata, 'general-dv4')


#getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-compute', vmsData, rawdata, 'compute')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/fsv2-series',             vmsData, rawdata, 'compute-fsv2')

#getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-memory', vmsData, rawdata, 'memory')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/dv2-dsv2-series-memory',  vmsData, rawdata, 'memory-dv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ev3-esv3-series',         vmsData, rawdata, 'memory-ev3')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/eav4-easv4-series',       vmsData, rawdata, 'memory-eav4')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/edv4-edsv4-series',       vmsData, rawdata, 'memory-edv4')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ev4-esv4-series',         vmsData, rawdata, 'memory-ev4')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/m-series',                vmsData, rawdata, 'memory-m')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/mv2-series',              vmsData, rawdata, 'memory-mv2')

#getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-storage', vmsData, rawdata, 'storage')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/lsv2-series', vmsData, rawdata, 'storage-lsv2')

#getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-gpu', vmsData, rawdata, 'gpu')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/nc-series',   vmsData, rawdata, 'gpu-nc')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ncv2-series', vmsData, rawdata, 'gpu-ncv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ncv3-series', vmsData, rawdata, 'gpu-ncv3')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/nd-series',   vmsData, rawdata, 'gpu-nd')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/ndv2-series', vmsData, rawdata, 'gpu-ndv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/nv-series',   vmsData, rawdata, 'gpu-nv')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/nvv3-series', vmsData, rawdata, 'gpu-nvv3')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/nvv4-series', vmsData, rawdata, 'gpu-nvv4')

#getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/windows/sizes-hpc', vmsData, rawdata, 'hpc')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/h-series',    vmsData, rawdata, 'hpc-h')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/hb-series',   vmsData, rawdata, 'hpc-hb')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/hbv2-series', vmsData, rawdata, 'hpc-hbv2')
getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/hc-series',   vmsData, rawdata, 'hpc-hc')

getVmSpecFromWebPage('https://docs.microsoft.com/en-us/azure/virtual-machines/sizes-previous-gen', vmsData, rawdata, 'prev-gen')



print('Processing specs...')

offers = vmsData['offers']
othersDebug = []

for row in rawdata:
    vm = {}
    vmid = ''
    tier = ''
    vmsize = ''
    if 'Size' in row:
        # Standard_A0
        # A0\Basic_A0
        vmid = row['Size']
        if vmid.endswith('*'):
            vmid = vmid[:-1]
        parts = vmid.split('_', 1)
        tier = parts[0].capitalize()
        vmsize = parts[1].replace('_', '').capitalize()
        print ('SIZE: ' + row['Size'] +  ' -> ' + vmid + ' |' + tier + ' _ ' + vmsize)
        row.pop('Size', None)
    elif 'Size – Size\\Name' in row:
        parts = row['Size – Size\\Name'].split('\\', 1)
        vmid = parts[1]
        parts = vmid.split('_', 1)
        tier = parts[0].capitalize()
        vmsize = parts[1].replace('_', '').capitalize()
        print ('SIZE: ' + row['Size – Size\\Name'] +  ' -> ' + vmid + ' |' + tier + ' _ ' + vmsize)
        row.pop('Size – Size\\Name', None)
    elif 'Scenario' in row:
        # not a VM spec
        continue
    else:
        print("Unk vmid: ")
        pprint(row)
        continue

    if vmid == '_' or vmid == '':
        continue

    # if vmid == 'Standard_F16s_v2':
    #     pass

    vmid = tier + "_" + vmsize

    if vmid in offers:
        print ("vmid found:" + vmid + " (" + row['source'] + ")" )
        row.pop('Memory', None)
        row.pop('Memory: GiB', None)
        row.pop('Memory (GiB)', None)
        row.pop('Memory (GB)', None)
        row.pop('vCPU', None)
        row.pop('vCPUs', None)
        row.pop('vCPU\'s', None)
        row.pop('vCore', None)
        row.pop('Size', None)
        row.pop('size', None)
        row.pop('series', None)
    else:
        print ("vmid not found:" + vmid + " (" + row['source'] + ")")
        offers[vmid] = { 'tier': tier, 'vmsize': vmsize, 'vmid': vmid }
        if 'Memory: GiB' in row:
            offers[vmid]['ram'] = float(row['Memory: GiB'].replace(',', ''))
            row.pop('Memory: GiB', None)
        elif 'Memory' in row:
            if row['Memory'].endswith('MB'):
                offers[vmid]['ram'] = float(row['Memory'].replace(' MB', '')) / 1024
            else: 
                offers[vmid]['ram'] = float(row['Memory'].replace(' GB', '').replace(' GiB', ''))
            row.pop('Memory', None)
        elif 'Memory (GiB)' in row:
            offers[vmid]['ram'] = float(row['Memory (GiB)'])
            row.pop('Memory (GiB)', None)

        if 'vCPU' in row:
            offers[vmid]['cores'] = int(row['vCPU'])
            row.pop('vCPU', None)
        elif 'vCPU&#39;s' in row:
            offers[vmid]['cores'] = int(row['vCPU&#39;s'])
            row.pop('vCPU&#39;s', None)
        elif 'vCPU\'s' in row:
            offers[vmid]['cores'] = int(row['vCPU\'s'])
            row.pop('vCPU\'s', None)
        elif 'vCore' in row:
            offers[vmid]['cores'] = int(row['vCore'])
            row.pop('vCore', None)
        if 'series' in row:
            offers[vmid]['series'] = row['series']
            row.pop('series', None)

    offers[vmid]['source'] = row['source']
    row.pop('source', None)
        
    if 'Temp storage (HDD): GiB' in row:
        offers[vmid]['tempsStorage'] = int(row['Temp storage (HDD): GiB'])
        offers[vmid]['tempsStorageType'] = "HDD"
        row.pop('Temp storage (HDD): GiB', None)
    elif 'Temp storage (GiB)' in row:
        parts = row['Temp storage (GiB)'].replace(" ", "").split("+", 1)
        offers[vmid]['tempsStorage'] = 0
        for v in parts:
            offers[vmid]['tempsStorage'] += int(v)
        # offers[vmid]['tempsStorage'] = int(row['Temp storage (GiB)'])
        row.pop('Temp storage (GiB)', None)
    elif 'Temp storage (GB)' in row: # Standard_HB120rs_v2 = '480 + 960'
        offers[vmid]['tempsStorage'] = (row['Temp storage (GB)'])
        row.pop('Temp storage (GB)', None)
    elif 'Max temporary disk size' in row:
        offers[vmid]['tempsStorage'] = int(row['Max temporary disk size'].replace(' GB', ''))
        row.pop('Max temporary disk size', None)
    elif 'Local SSD: GiB' in row:
        offers[vmid]['tempsStorage'] = int(row['Local SSD: GiB'])
        offers[vmid]['tempsStorageType'] = "SSD"
        row.pop('Local SSD: GiB', None)
    elif 'Temp storage (SSD) GiB' in row:
        if row['Temp storage (SSD) GiB'] == 'Remote Storage Only':
            offers[vmid]['tempsStorage'] = 0
            offers[vmid]['tempsStorageType'] = "None"
        else:
            offers[vmid]['tempsStorage'] = int(row['Temp storage (SSD) GiB'].replace(',', ''))
            offers[vmid]['tempsStorageType'] = "SSD"
        row.pop('Temp storage (SSD) GiB', None)
    if 'Temp storage (SSD): GiB' in row:   # Simple IF car il semble que cette propriété soit en double avec une autre ...
        offers[vmid]['tempsStorage'] = int(row['Temp storage (SSD): GiB'])
        offers[vmid]['tempsStorageType'] = "SSD"
        row.pop('Temp storage (SSD): GiB', None)
    elif 'Temp Storage (SSD): GiB' in row:   # Simple IF car il semble que cette propriété soit en double avec une autre ...
        offers[vmid]['tempsStorage'] = int(row['Temp Storage (SSD): GiB'])
        offers[vmid]['tempsStorageType'] = "SSD"
        row.pop('Temp Storage (SSD): GiB', None)
    elif 'Temp disk<sup>1</sup> (GiB)' in row:
        offers[vmid]['tempsStorage'] = int(row['Temp disk<sup>1</sup> (GiB)'])
        row.pop('Temp disk<sup>1</sup> (GiB)', None)   

    if 'Max data disks' in row:
        offers[vmid]['dataDisks'] = int(row['Max data disks'])
        row.pop('Max data disks', None)
    if 'Max Data Disks' in row:
        offers[vmid]['dataDisks'] = int(row['Max Data Disks'])
        row.pop('Max Data Disks', None)        
    elif 'Maximum data disks' in row:
        offers[vmid]['dataDisks'] = int(row['Maximum data disks'])
        row.pop('Maximum data disks', None)
    elif 'Max. data disks (1023 GB each)' in row:
        offers[vmid]['dataDisks'] = int(row['Max. data disks (1023 GB each)'])
        row.pop('Max. data disks (1023 GB each)', None)
        
    if 'Max data disk throughput: IOPS' in row:
        offers[vmid]['iops'] = parseIops(row['Max data disk throughput: IOPS'])
        row.pop('Max data disk throughput: IOPS', None)
    elif 'Max. IOPS (300 per disk)' in row:
        offers[vmid]['iops'] = parseIops(row['Max. IOPS (300 per disk)'])
        row.pop('Max. IOPS (300 per disk)', None)
    elif 'Throughput: IOPS' in row:
        offers[vmid]['iops'] = parseIops(row['Throughput: IOPS'])
        row.pop('Throughput: IOPS', None)
    elif 'Max uncached disk perf: IOPS / MBps' in row:
        parts = row['Max uncached disk perf: IOPS / MBps'].split(" / ", 1)
        offers[vmid]['iops'] = int(parts[0])
        offers[vmid]['MBps'] = float(parts[1])
        row.pop('Max uncached disk perf: IOPS / MBps', None)
    elif 'Max data disks / throughput: IOPS' in row:
        parts = row['Max data disks / throughput: IOPS'].replace(' ', '').split('/', 1)
        offers[vmid]['dataDisks'] = int(parts[0])
        offers[vmid]['iops'] = parseIops(parts[1])
        row.pop('Max data disks / throughput: IOPS', None)
    elif 'Max data disks/throughput: IOPS'  in row:
        parts = row['Max data disks/throughput: IOPS'].split('/', 2)
        offers[vmid]['dataDisks'] = int(parts[0])
        offers[vmid]['iops'] = parseIops(parts[1])
        row.pop('Max data disks/throughput: IOPS', None)
    elif 'Max uncached disk throughput: IOPS / MBps' in row:
        parts = row['Max uncached disk throughput: IOPS / MBps'].replace(" ", "").split("/", 1)
        if(len(parts) > 1 and parts[0] != '' ):
            offers[vmid]['iops'] = int(parts[0].replace(',', ''))
            offers[vmid]['MBps'] = float(parts[1].replace(',', ''))
        row.pop('Max uncached disk throughput: IOPS / MBps', None)
    elif 'Max uncached disk throughput: IOPS/MBps' in row:
        parts = row['Max uncached disk throughput: IOPS/MBps'].replace(" ", "").split("/", 1)
        if(len(parts) > 1 and parts[0] != '' ):
            offers[vmid]['iops'] = int(parts[0].replace(',', ''))
            offers[vmid]['MBps'] = float(parts[1].replace(',', ''))
        row.pop('Max uncached disk throughput: IOPS/MBps', None)
    elif 'Max uncached disk throughput (IOPS / MBps)' in row:
        parts = row['Max uncached disk throughput (IOPS / MBps)'].replace(" ", "").split("/", 1)
        offers[vmid]['iops'] = int(parts[0].replace(',', ''))
        offers[vmid]['MBps'] = float(parts[1].replace(',', ''))
        row.pop('Max uncached disk throughput (IOPS / MBps)', None)
    elif 'Max uncached disk throughput (IOPS/MBps)' in row:
        parts = row['Max uncached disk throughput (IOPS/MBps)'].replace(" ", "").split("/", 1)
        offers[vmid]['iops'] = int(parts[0].replace(',', ''))
        offers[vmid]['MBps'] = float(parts[1].replace(',', ''))
        row.pop('Max uncached disk throughput (IOPS/MBps)', None)
    elif 'Max uncached data disk throughput (IOPs/MBps)<sup>4</sup>' in row:
        parts = row['Max uncached data disk throughput (IOPs/MBps)<sup>4</sup>'].replace(" ", "").split("/", 1)
        offers[vmid]['iops'] = int(parts[0].replace(',', ''))
        offers[vmid]['MBps'] = float(parts[1].replace(',', ''))
        row.pop('Max uncached data disk throughput (IOPs/MBps)<sup>4</sup>', None)
    elif 'Max disk throughput: IOPS' in row:
        offers[vmid]['iops'] = parseIops(row['Max disk throughput: IOPS'])
        row.pop('Max disk throughput: IOPS', None)

    if 'Max temp storage throughput: IOPS / Read MBps / Write MBps' in row:
        parts = row['Max temp storage throughput: IOPS / Read MBps / Write MBps'].split('/', 2)
        if(len(parts) > 2 and parts[0] != ''):
            offers[vmid]['tempsStorageIops'] = int(parts[0])
            offers[vmid]['tempsStorageMBpsRead'] = int(parts[1])
            offers[vmid]['tempsStorageMBpsWrite'] = int(parts[2])
        # else:
        #     print('DEBUG: ' + vmid + ' - Max temp storage throughput: IOPS / Read MBps / Write MBps - "' + row['Max temp storage throughput: IOPS / Read MBps / Write MBps'] + '"') 
        row.pop('Max temp storage throughput: IOPS / Read MBps / Write MBps', None)
    elif 'Max temp storage throughput: IOPS/Read MBps/Write MBps' in row:
        parts = row['Max temp storage throughput: IOPS/Read MBps/Write MBps'].split('/', 2)
        if(len(parts) > 2 and parts[0] != ''):
            offers[vmid]['tempsStorageIops'] = int(parts[0])
            offers[vmid]['tempsStorageMBpsRead'] = int(parts[1])
            offers[vmid]['tempsStorageMBpsWrite'] = int(parts[2])
        # else:
        #     print('DEBUG: ' + vmid + ' - Max temp storage throughput: IOPS / Read MBps / Write MBps - "' + row['Max temp storage throughput: IOPS / Read MBps / Write MBps'] + '"') 
        row.pop('Max temp storage throughput: IOPS/Read MBps/Write MBps', None)
        
    if 'Max cached and temp storage throughput: IOPS / MBps' in row:
        parts = row['Max cached and temp storage throughput: IOPS / MBps'].split('/', 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
        offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
        offers[vmid]['tempsStorageMBps'] = float(parts[1].replace(',', '').strip())
        offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
        row.pop('Max cached and temp storage throughput: IOPS / MBps', None)
    elif 'Max cached and temp storage throughput: IOPS/MBps' in row:
        parts = row['Max cached and temp storage throughput: IOPS/MBps'].split('/', 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
        offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
        offers[vmid]['tempsStorageMBps'] = float(parts[1].replace(',', '').strip())
        offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
        row.pop('Max cached and temp storage throughput: IOPS/MBps', None)
    elif '<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps' in row:
        parts = row['<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps'].split('/', 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
        offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
        offers[vmid]['tempsStorageMBps'] = float(parts[1].replace(',', '').strip())
        offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
        row.pop('<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps', None)
    elif 'Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)' in row:
        # '4,000 / 32 (50)' or '128,000 / 1024 (1600)' or '128000/1024 (1600)' or '144000 (1520)'
        # try:
            parts = row['Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)'].split('/', 1)
            if len(parts) == 2:
                parts2 = parts[1].split(' (', 1)
                offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
                offers[vmid]['tempsStorageMBps'] = int(parts2[0].replace(',', '').strip())
                offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
                offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
                if len(parts2) == 2:
                    offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
            elif parts[0] != '':
                parts2 = parts[0].split(' (', 1)
                offers[vmid]['tempsStorageIops'] = int(parts2[0].replace(',', '').strip())
                offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
                offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
            # else:
            #     print('DEBUG: ' + vmid + ' - Max cached and temp storage throughput: IOPS / MBps (cache size in GiB) - "' + row['Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)'] + '"') 
            row.pop('Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)', None)
        # except Exception as ex:
        #     print("Failed to process  '" + offers[vmid]['source'] + "'.'" + vmid + "'.'Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)'= '" + row['Max cached and temp storage throughput: IOPS / MBps (cache size in GiB)'] + "'")
        #     print(ex)
    elif 'Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)' in row:
        # '4,000 / 32 (50)' or '128,000 / 1024 (1600)' or '128000/1024 (1600)' or '144000 (1520)'
        parts = row['Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)'].split('/', 1)
        if(len(parts) == 2):
            parts2 = parts[1].replace(' ', '').split('(', 1)
            offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
            offers[vmid]['tempsStorageMBps'] = int(parts2[0].replace(',', '').strip())
            offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
            offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
            offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
        elif( parts[0] != '' ):
            parts2 = parts[0].replace(' ', '').split('(', 1)
            offers[vmid]['tempsStorageIops'] = int(parts2[0].replace(',', '').strip())
            offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
            offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
        row.pop('Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)', None)
    elif '<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)' in row:
        # '4,000 / 32 (50)' or '128,000 / 1024 (1600)' or '128000/1024 (1600)' or '144000 (1520)'
        parts = row['<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)'].split('/', 1)
        if(len(parts) == 2):
            parts2 = parts[1].replace(' ', '').split('(', 1)
            offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
            offers[vmid]['tempsStorageMBps'] = int(parts2[0].replace(',', '').strip())
            offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
            offers[vmid]['cachedMBps'] = offers[vmid]['tempsStorageMBps']
            offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
        elif( parts[0] != '' ):
            parts2 = parts[0].replace(' ', '').split('(', 1)
            offers[vmid]['tempsStorageIops'] = int(parts2[0].replace(',', '').strip())
            offers[vmid]['cachedIops'] = offers[vmid]['tempsStorageIops']
            offers[vmid]['ioCache'] = int(parts2[1].replace(',', '').replace(')', ''))
        row.pop('<sup>**</sup> Max cached and temp storage throughput: IOPS/MBps (cache size in GiB)', None)
    elif 'Max cached throughput: IOPS/MBps (cache size in GiB)' in row:
        parts = row['Max cached throughput: IOPS/MBps (cache size in GiB)'].replace(' ', '').replace(',', '').split('/', 1)
        parts2 = parts[1].split('(', 1)
        offers[vmid]['cachedIops'] = int(parts[0])
        offers[vmid]['cachedMBps'] = int(parts2[0])
        offers[vmid]['ioCache'] = int(parts2[1].replace(')', ''))
        row.pop('Max cached throughput: IOPS/MBps (cache size in GiB)', None)

    if 'Max local disk perf: IOPS / MBps' in row:
        parts = row['Max local disk perf: IOPS / MBps'].replace(' ', '').split("/", 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0])
        offers[vmid]['tempsStorageMBps'] = float(parts[1])
        row.pop('Max local disk perf: IOPS / MBps', None)
    if 'Max temp storage throughput (IOPS / MBps)' in row: 
        parts = row['Max temp storage throughput (IOPS / MBps)'].replace(' ', '').split("/", 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0])
        offers[vmid]['tempsStorageMBps'] = float(parts[1])
        row.pop('Max temp storage throughput (IOPS / MBps)', None)
    if 'Max temp storage throughput (IOPS/MBps)' in row: 
        parts = row['Max temp storage throughput (IOPS/MBps)'].replace(' ', '').split("/", 1)
        offers[vmid]['tempsStorageIops'] = int(parts[0])
        offers[vmid]['tempsStorageMBps'] = float(parts[1])
        row.pop('Max temp storage throughput (IOPS/MBps)', None)
        
        
    if 'Max NICs / Expected network bandwidth (Mbps)' in row:
        # try:
            parts = row['Max NICs / Expected network bandwidth (Mbps)'].replace(' ', '').split('/', 1)
            if(len(parts) == 2):
                offers[vmid]['nic'] = int(parts[0])
                offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
            else:
                offers[vmid]['nicMbps'] = int(parts[0].replace(',', '').replace('+', ''))
            row.pop('Max NICs / Expected network bandwidth (Mbps)', None)
    elif 'Max NICs/Expected network bandwidth (Mbps)' in row:
        # try:
            parts = row['Max NICs/Expected network bandwidth (Mbps)'].replace(' ', '').split('/', 1)
            if(len(parts) == 2):
                offers[vmid]['nic'] = int(parts[0])
                offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
            else:
                offers[vmid]['nicMbps'] = int(parts[0].replace(',', '').replace('+', ''))
            row.pop('Max NICs/Expected network bandwidth (Mbps)', None)
        # except Exception as ex:
        #     print("Failed to process '" + offers[vmid]['source'] + "'.'" + vmid + "'.'Max NICs / Expected network bandwidth (Mbps)'= '" + row['Max NICs / Expected network bandwidth (Mbps)'] + "'")
        #     print(ex)
    elif 'Max NICs / Network bandwidth' in row:
        parts = row['Max NICs / Network bandwidth'].replace(' ', '').split('/', 1)
        offers[vmid]['nic'] = int(parts[0])
        offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
        row.pop('Max NICs / Network bandwidth', None)
    elif 'Max NICs/Network bandwidth' in row:
        parts = row['Max NICs/Network bandwidth'].replace(' ', '').split('/', 1)
        offers[vmid]['nic'] = int(parts[0])
        offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
        row.pop('Max NICs/Network bandwidth', None)
    elif 'Max NICs / Expected network bandwidth (MBps)' in row:
        parts = row['Max NICs / Expected network bandwidth (MBps)'].replace(' ', '').split('/', 1)
        if len(parts) > 1:
            offers[vmid]['nic'] = int(parts[0])
            offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
        row.pop('Max NICs / Expected network bandwidth (MBps)', None)
    elif 'Max NICs / Network bandwidth (Mbps)' in row:
        parts = row['Max NICs / Network bandwidth (Mbps)'].replace(' ', '').split('/', 1)
        offers[vmid]['nic'] = int(parts[0])
        offers[vmid]['nicMbps'] = int(parts[1].replace(',', '').replace('+', ''))
        row.pop('Max NICs / Network bandwidth (Mbps)', None)
    elif 'Max Ethernet NICs' in row:
        offers[vmid]['nic'] = int(row['Max Ethernet NICs'])
        row.pop('Max Ethernet NICs', None)
    else:
        if 'Max NICs' in row:
            parts = row['Max NICs'].replace(' ', '').split('/', 1)
            offers[vmid]['nic'] = int(parts[0])
            if len(parts) == 2:
                offers[vmid]['nicMbps'] = int(parts[1])
            row.pop('Max NICs', None)
        elif 'NICs (Max)' in row:
            offers[vmid]['nic'] = int(row['NICs (Max)'])
            row.pop('NICs (Max)', None)
        elif 'Max Ethernet vNICs' in row:
            offers[vmid]['nic'] = int(row['Max Ethernet vNICs'])
            row.pop('Max Ethernet vNICs', None)
        if 'Max network bandwidth' in row:
            offers[vmid]['nicMbps'] = int(row['Max network bandwidth'].replace(' Mbps', ''))
            row.pop('Max network bandwidth', None)
        elif 'Expected network bandwidth (Mbps)' in row:
            if row['Expected network bandwidth (Mbps)'] != '':
                offers[vmid]['nicMbps'] = int(row['Expected network bandwidth (Mbps)'].replace('+', ''))
            row.pop('Expected network bandwidth (Mbps)', None)
        elif 'Expected network bandwidth (MBps)' in row:  # uppercase 'B' MBps
            if row['Expected network bandwidth (MBps)'] != '':
                offers[vmid]['nicMbps'] = int(row['Expected network bandwidth (MBps)'].replace('+', ''))
            row.pop('Expected network bandwidth (MBps)', None)
        elif 'Expected Network bandwidth (Mbps)' in row:  # uppercase 'N' Network
            if row['Expected Network bandwidth (Mbps)'] != '':
                offers[vmid]['nicMbps'] = int(row['Expected Network bandwidth (Mbps)'].replace('+', ''))
            row.pop('Expected Network bandwidth (Mbps)', None)
        elif 'Network bandwidth' in row:
            offers[vmid]['nicMbps'] = int(row['Network bandwidth'])  # .replace(' Mbps', ''))
            row.pop('Network bandwidth', None)
            

    # Processor model
    if 'Processor' in row:
        offers[vmid]['processor'] = row['Processor'].replace('Intel Xeon ', 'Xeon')
        row.pop('Processor', None)


    # serie L
    if 'NVMe Disks<sup>2</sup>' in row:  # example: "2x1.92 TB"
        parts = row['NVMe Disks<sup>2</sup>'].split("x", 1)
        offers[vmid]['tempsStorage'] = int(parts[0]) * float(parts[1].replace("TB", "").strip()) * 1024
        offers[vmid]['tempsStorageType'] = "NVMe"
        row.pop('NVMe Disks<sup>2</sup>', None) 
    if 'NVMe Disk throughput<sup>3</sup> (Read IOPS / MBps)' in row: # examples: "800000 / 4000" "1.5M / 8000"
        parts = row['NVMe Disk throughput<sup>3</sup> (Read IOPS / MBps)'].replace(" ", "").split("/", 1)
        if parts[0].endswith('M'):
            offers[vmid]['tempsStorageIops'] = float(parts[0].replace(',', '').replace('M', '').strip()) * 1000000
        else:
            offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
        offers[vmid]['tempsStorageMBps'] = int(parts[1].replace(',', '').strip())
        offers[vmid]['tempsStorageType'] = "NVMe"
        row.pop('NVMe Disk throughput<sup>3</sup> (Read IOPS / MBps)', None)
    if 'NVMe Disk throughput<sup>3</sup> (Read IOPS/MBps)' in row: # examples: "800000 / 4000" "1.5M / 8000"
        parts = row['NVMe Disk throughput<sup>3</sup> (Read IOPS/MBps)'].replace(" ", "").split("/", 1)
        if parts[0].endswith('M'):
            offers[vmid]['tempsStorageIops'] = float(parts[0].replace(',', '').replace('M', '').strip()) * 1000000
        else:
            offers[vmid]['tempsStorageIops'] = int(parts[0].replace(',', '').strip())
        offers[vmid]['tempsStorageMBps'] = int(parts[1].replace(',', '').strip())
        offers[vmid]['tempsStorageType'] = "NVMe"
        row.pop('NVMe Disk throughput<sup>3</sup> (Read IOPS/MBps)', None)


    # series B
    if 'Base Perf of a Core' in row:
        offers[vmid]['basePerfOfACore'] = row['Base Perf of a Core']
        row.pop('Base Perf of a Core', None)
    if 'Credits banked / hour' in row:
        offers[vmid]['creditsBankedPerHour'] = int(row['Credits banked / hour'])
        row.pop('Credits banked / hour', None)
    if 'Credits banked/hour' in row:
        offers[vmid]['creditsBankedPerHour'] = int(row['Credits banked/hour'])
        row.pop('Credits banked/hour', None)
    if 'Max Banked Credits' in row:
        offers[vmid]['maxBankedCredits'] = row['Max Banked Credits']
        row.pop('Max Banked Credits', None)

    # GPU
    if 'GPU' in row:
        offers[vmid]['GPU'] = row['GPU']
        row.pop('GPU', None)
    if 'GPU Memory: GiB' in row.keys():
        offers[vmid]['GPUMem'] = row['GPU Memory: GiB']
        row.pop('GPU Memory: GiB', None)
    elif 'GPU memory: GiB' in row.keys():
        offers[vmid]['GPUMem'] = row['GPU memory: GiB']
        row.pop('GPU memory: GiB', None)

    # for key in row.keys():
    #     print("debug key " + key)

    if len(row.keys()) != 0:
        offers[vmid]['other'] = row
        for key in row.keys():
            if key not in othersDebug:
                othersDebug.append(key)
# end for row in rawdata:

print ('othersDebug: ')
pprint(othersDebug)

refCores = vmsData['refCores']
refRam = vmsData['refRam']
for vmid in offers:
    if 'cores' in offers[vmid]:
        if not offers[vmid]['cores'] in refCores:
            refCores.append( offers[vmid]['cores'])
    if 'ram' in offers[vmid]:
        if not offers[vmid]['ram'] in refRam:
            refRam.append( offers[vmid]['ram'])

vmsData['refCores'].sort()
vmsData['refRam'].sort()
vmsData['refDatacenter'].sort()


# Sorter for offers to put windows and linux first
def offerSorter(offer):
    if(offer == 'windows'):
        return '1' + offer
    elif(offer == 'linux'):
        return '2' + offer
    else:
        return '3' + offer
vmsData['refOffers'].sort(key=offerSorter)


#print(pformat(vmsData, indent = 1).replace('₹', 'INR').replace('РУБ', 'RUB').replace('₺&nbsp', 'TRY').encode())
#print(pformat(vmsData, indent = 1).replace('₹', 'INR').replace('РУБ', 'RUB').replace('₺&nbsp', 'TRY'))

with open('AzureVMData.js', 'w') as outfile:
    json.dump(vmsData, outfile, indent = 1, sort_keys = True)

print ("fin")
