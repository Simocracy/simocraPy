#!/usr/bin/python
# -*- coding: UTF-8 -*-

import urllib.request, urllib.parse, urllib.error, urllib.request, urllib.error, urllib.parse, http.cookiejar
import xml.etree.ElementTree as ET
import re
import simocracy.credentials as credentials

username = credentials.username
password = credentials.password

url = 'http://simocracy.de/'
vz = "Wikocracy:Portal"
sortprefixes = [
    'Königreich',
    'Republik',
    'Bundesrepublik',
    'Föderation',
    'Reich',
    'Heiliger',
    'Heilige',
    'Hl.',
]

"""
Loggt den User ins Wiki ein.
Gibt den eingeloggten URL-Opener zurueck.
"""
def login(username, password):
    #Ersten Request zusammensetzen, der das Login-Token einsammelt
    query_args = { 'lgname':username, 'lgpassword':password }
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    response = opener.open(url + 'api.php?format=xml&action=login', urllib.parse.urlencode(query_args).encode('utf8'))

    #Token aus xml extrahieren
    response.readline() #Leerzeile überspringen
    xmlRoot = ET.fromstring(response.readline())
    lgToken = xmlRoot.find('login').attrib['token']
    session = xmlRoot.find('login').attrib['sessionid']

    #Zweiter Request mit Login-Token
    query_args.update({'lgtoken':lgToken})
    data = urllib.parse.urlencode(query_args)
    response = opener.open(url+'api.php?format=xml&action=login', data.encode('utf8'))

    #Login-Status; ggf. abbrechen
    response.readline() #Leerzeile überspringen
    xmlRoot = ET.fromstring(response.readline())
    result = xmlRoot.find('login').attrib['result']

    if result != "Success":
        raise Exception("Login: " + result)
    else:
        print(("Login: " + result))
	
    return opener

"""
Liest Staaten und Bündnisse aus dem
Verzeichnis-Seitentext site aus und packt sie in ein dict.
Keys: staaten, buendnisse

staaten: Liste aus dicts; keys:
nummer
flagge (bild-URL)
name
uri (Artikelname)
buendnis (flaggen-URL)
ms
as
spieler
zweitstaat

buendnisse: array aus dicts; keys:
    flagge
    name
    
zB Zugriff auf Staatenname: r["staaten"][0]["name"]
"""
def readVZ(site, opener):

    if not site:
        raise Exception("übergebene Seite leer")
    text = []
    for line in site:
        text.append(line)
    del site
        
    """
    Staaten
    """
    # "|Staaten=" suchen
    i = 0
    found = False
    while True:
        if re.match(b'^\s*|\s*Staaten\s*=\s*', text[i]):
            i += 1
            found = True
            break
        i += 1
    if not found:
        raise Exception("|Staaten= nicht gefunden.")
    found = False
    
    # erstes "{{!}}-" suchen
    while True:
        if text[i].startswith(b'{{!}}-'):
            found = True
            i += 1
            break
        i += 1
    if not found:
        raise Exception("Staatentabellenheader nicht gefunden.")
    found = False
    
    # zweites "{{!}}-" suchen
    while True:
        if text[i].startswith(b'{{!}}-'):
            found = True
            i += 1
            break
        i += 1
    if not found:
        raise Exception("Staatentabelleninhalt nicht gefunden.")
    found = False
    
    #Tabelle parsen
    entryCtr = 0
    dict = {}
    staaten = []
    #gegen highlightbug X_x
    ta = "'" + "'" + "'"
    name_p = re.compile(r'\{\{!\}\}\s*'+ta+'\s*(\[\[[^]]*\]\])\s*'+ta+'\s*<br>\s*(.*)')
    flagge_p = re.compile(r'\{\{!\}\}\s*(\[\[[^]]*\]\])\s*')
    zahl_p = re.compile(r'\{\{!\}\}\s*(\(*[\d-]*\)*)\s*')
    while True:
        #Tabellenende
        if text[i].startswith(b'{{!}}}'):
            i += 1
            break
        #Tabelleneintrag
        if not text[i].startswith(b'{{!}}'):
            i += 1
            continue
        
        #Datensatz zuende
        if text[i].startswith(b'{{!}}-'):
            if entryCtr == 5:
                staaten.append(dict.copy())
                dict.clear()
            i += 1
            entryCtr = 0
            continue
            
        key = ""
        value = text[i].strip().decode('utf-8')
        
        #Ins dict eintragen; evtl value korrigieren
        if entryCtr == 0:
            value = value.replace('{{!}}', '').strip()
            try:
                dict["flagge"] = extractFlag(value, opener)
            except:
                raise Exception("fehler bei Flaggencode "+value)
            
        elif entryCtr == 1:
            tokens = re.split(name_p, value)
            names = getStateNames(tokens[1])
            dict["name"] = names["name"]
            dict["uri"] = names["uri"]
            dict["sortname"] = names["sortname"]


            #Spielername
            dict["spieler"] = tokens[2].replace('[[', '').replace(']]', '')
            
        elif entryCtr == 2:
            try:
                value = re.split(flagge_p, value)[1]
                dict["buendnis"] = extractFlag(value, opener)
            except:
                dict["buendnis"] = ""
            
        elif entryCtr == 3:
            ms = re.split(zahl_p, value)[1]
            #Zweitstaat
            if ms.startswith('('):
                ms = ms.replace('(', '').replace(')', '')
                dict["zweitstaat"] = True
            else:
                dict["zweitstaat"] = False
            dict["ms"] = ms
            
        elif entryCtr == 4:
            bomben = re.split(zahl_p, value)[1]
            if bomben == '-':
                bomben = '0'
            dict["as"] = bomben
            
        entryCtr += 1
        i += 1
        
        if i == len(text):
            break

    """
    Spielerlose Staaten
    """
    #"|Spielerlose_Staaten=" suchen
    found = False
    while True:
        line = text[i].decode('utf-8')
        if i >= len(text):
            break
        if re.match(r'\s*\|\s*Spielerlose_Staaten\s*=', line) is not None:
            i += 1
            found = True
            break
        i += 1
    if not found:
        raise Exception("|Spielerlose_Staaten= nicht gefunden.")

    #Tabelle parsen
    eintrag_p = re.compile(r'\*(\{\{[^\}]+\}\})\s*(\[\[[^]]+\]\])')
    dict = {}
    spielerlos = []
    while True:
        line = text[i].decode('utf-8')
        #Tabellenende
        if line.startswith("|") or i >= len(text):
            break
        if eintrag_p.match(line) is not None:
            tokens = re.split(eintrag_p, line)
            dict["flagge"] = extractFlag(tokens[1], opener)
            names = getStateNames(tokens[2])
            dict["uri"] = names["uri"]
            dict["name"] = names["name"]
            dict["sortname"] = names["sortname"]
            spielerlos.append(dict.copy())
            dict.clear()
            i += 1
            continue
        i += 1
    
    """
    Bündnisse
    """
    #"|Militärbündnisse" suchen
    found = False
    while True:
        line = text[i].decode('utf-8')
        if i >= len(text):
            break
        if re.match(r'^\s*|\s*Milit', line) is not None and re.search(r'ndnisse\s*=\s*$', line) is not None:
            i += 1
            found = True
            break
        i += 1
    if not found:
        raise Exception("|Militärbündnisse= nicht gefunden.")
    found = False
    
    #Tabelle parsen
    entryCtr = 0
    dict = {}
    bnds = []
    bndeintrag_p = re.compile(r'\*\s*(\[\[[^]]*\]\])\s*\[\[([^]]*)\]\]')
    while True:
        line = text[i].decode('utf-8')
        #Tabellenende
        if line.startswith('{{!}}'):
            i += 1
            break
        #Tabelleneintrag
        if bndeintrag_p.match(line) is not None:
            tokens = re.split(bndeintrag_p, line)
            dict["flagge"] = extractFlag(tokens[1], opener).strip()
            dict["name"] = tokens[2].split("|")[0].strip()
            bnds.append(dict.copy())
            dict.clear()
            i += 1
            continue

        i += 1
        
        if i == len(text):
            break
    
    return {
            "staaten": sorted(staaten, key=lambda k: k['sortname']),
            "buendnisse":bnds,
            "spielerlos": sorted(spielerlos, key=lambda k: k['uri']),
    }

"""
Nimmt einen Wikilink der Form [[x|y]] oder [[x]] und
liefert Staatsname, Staats-URI und Sortierkey zurück:
{ "name":name, "uri":uri, "sortname":sortname }
"""
def getStateNames(wikilink):
    name_p = re.compile(r'\[\[([^]]*)\]\]')

    r = {}
    #Staatsname
    tokens = re.split(name_p, wikilink)
    values = tokens[1].split("|")
    name = values[len(values) - 1]
    name = name.strip()
    r["name"] = name

    #URI; fuer [[x|y]]
    r["uri"] = values[0].strip()

    #Name für Sortierung
    sortkey = name
    for el in sortprefixes:
        if sortkey.startswith(el+' '):
            sortkey = sortkey.replace(el, '')
            sortkey = sortkey.strip()
    r["sortname"] = sortkey
    return r
    
"""
Extrahiert den Dateinamen der Flagge
aus der Flaggeneinbindung flagcode.
Für den Fall der Flaggenvorlage wird
diese mit dem urlopener geöffnet.
"""
def extractFlag(flagcode, urlopener):
    #Flaggenvorlage
    if re.match(r'\{\{', flagcode) is not None:
        #flagcode.replace(r"{{", "")
        #flagcode.replace(r"|40}}", "")
        mitPx_p = re.compile(r'\{\{(.+?)\|\d*\}\}')
        ohnePx_p = re.compile(r'\{\{(.+?)\}\}')
        pattern = None
        if mitPx_p.match(flagcode):
            pattern = mitPx_p
        elif ohnePx_p.match(flagcode):
            pattern = ohnePx_p
        else:
            raise Exception(flagcode + " unbekannter Flaggencode")

        flagcode = re.split(pattern, flagcode)[1]
        
        #Vorlage herunterladen
        try:
            response = openArticle("Vorlage:" + flagcode, urlopener)
        except:
            raise Exception("konnte nicht öffnen: "+flagcode)
        text = []

        for line in response:
            line = line.decode('utf-8')
            if re.match(r'include>', line):
                break
        
        #Regex
        line = line.replace("Datei:", "")
        line = line.replace("datei:", "")
        line = line.replace("Bild:", "")
        line = line.replace("bild:", "")
        line = line.replace("Image:", "")
        line = line.replace("image:", "")
        pattern = re.compile(r"\[\[(.+?)\|.+?\]\]")
        flagcode = re.findall(pattern, line)[0]

    #Normale Bildeinbindung
    elif re.match(r'\[\[', flagcode) is not None:
        flagcode = flagcode.replace('[[', '')
        flagcode = flagcode.replace(']]', '')
        flagcode = flagcode.replace('Image:', '')
        flagcode = flagcode.replace('image:', '')
        flagcode = flagcode.replace('Bild:', '')
        flagcode = flagcode.replace('bild:', '')
        flagcode = flagcode.replace('Datei:', '')
        flagcode = flagcode.replace('datei:', '')
        values = flagcode.split('|')
        flagcode = values[0]
    #kaputt
    else:
        raise Exception(value + " keine gültige Flagge")
    
    #Bild-URL extrahieren
    flagcode = urllib.parse.quote(flagcode.strip().replace(' ', '_'))
    response = urlopener.open(url + 'api.php?titles=Datei:'+flagcode+'&format=xml&action=query&prop=imageinfo&iiprop=url')
    response.readline() #Leerzeile ueberspringen
    xmlRoot = ET.fromstring(response.readline())
    
    for element in xmlRoot.iterfind('query/pages/page/imageinfo/ii'):
        return element.attrib['url']


"""
Oeffnet einen Wikiartikel; loest insb. Redirections auf.
Gibt ein "file-like object" (doc)  zurueck.
article: Artikelname
opener: eingeloggter urlopener
"""
def openArticle(article, opener):
    response = opener.open(url + "api.php?format=xml&action=query&titles=" + urllib.parse.quote(article) + "&redirects")
    
    #Leerzeile ueberspringen
    response.readline()

    #XML einlesen
    xml = ET.fromstring(response.readline())

    article = xml.find("query").find("pages").find("page").attrib["title"]
    try:
        return opener.open(url + urllib.parse.quote(article) + "?action=raw")
    except urllib.error.HTTPError:
        raise Exception("404: " + article)


"""
Parst das erste Vorkommnis der Vorlage template im Artikel text
und gibt ein dict zurueck.
"""
def parseTemplate(template, site):
    dict = {}
    #Anfang der Vorlage suchen
    pattern = re.compile(r"\s*\{\{\s*"+re.escape(template)+"\s*$", re.IGNORECASE)
    for line in site:
        line = line.decode('utf8')
        if pattern.search(line) is not None:
            break

    pattern = re.compile(r"^\s*\|\s*([^=]*)\s*=\s*(.+)\s*$")
    for line in site:
        line = line.decode('utf-8')
        if re.match(r'\s*\}\}', line):
            if dict == {}:
                return None
            return dict
        if pattern.match(line) is not None:
            kvPair = re.findall(pattern, line)
            value = kvPair[0][1]
            if re.match(r'<!--(.*?)-->$', value):
                dict[kvPair[0][0]] = None
            else:
                dict[kvPair[0][0]] = value


"""
Schreibt den Text text in den Artikel article.
Opener ist der eingeloggte opener.
"""
def editArticle(article, text, opener):
    print("Bearbeite "+article)

    #Edit-Token lesen
    response = opener.open(url + 'api.php?action=query&format=xml&titles=' + urllib.parse.quote(article) + '&meta=tokens')
    #return response
    response.readline()
    xmlRoot = ET.fromstring(response.readline())
    editToken = xmlRoot.find('query').find('tokens').attrib['csrftoken']
    
    #Seite bearbeiten
    query_args = { 'text':text, 'token':editToken }
    query_url = url + 'api.php?action=edit&bot&format=xml&title=' + urllib.parse.quote(article)
    response = opener.open(query_url, urllib.parse.urlencode(query_args).encode('utf8'))

    #Result auslesen
    return response
    response.readline()
    xmlRoot = ET.fromstring(response.readline())
    if xml.find('edit').attrib['result'] != 'Success':
        raise Exception('edit not successful')