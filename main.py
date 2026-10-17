from enum import Enum
import keyring
from playwright.sync_api import BrowserContext
import typer
import requests
import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

app = typer.Typer()

config_file_path=Path.home()/".circle_cli_config.json"

SERVICE_NAME="circle_cli_tool"

MAXIMUM_ATTEMPTS=3

class Szerver(str,Enum):
    fured="fured"
    smallville="smallville"
class ScopeOption(str,Enum):
    all="all"
    vps="vps"
    auth="auth"
class Operation(str,Enum):
    sleep="sleep"
    wake_up="wake_up"
    reboot="reboot"
    reset="reset"
    renew="renew"
    shutdown="shutdown"
    shut_off="shut_off"
def get_config()->dict:
    if not config_file_path.exists(): return dict()
    with open(config_file_path,"r+") as conf:
        return json.load(conf)
def set_config(config_in:dict):
    with open(config_file_path,"w+") as conf:
        return json.dump(config_in,conf)
def retrieveCookies(s:Szerver)->dict:
    servers=get_config().get("servers")
    if servers==None: return None
    return servers.get(s.value)
def storeCookies(s:Szerver, cookies:dict):
    config=get_config()
    servers=config.get("servers",dict())
    servers[s.value]=cookies
    config["servers"]=servers
    set_config(config)
def storeNamedVM(name:str,s:Szerver,id:int):
    config=get_config()
    vms=config.get("vms",dict())
    vm=vms.get(name,dict())
    vm["id"]=id
    vm["server"]=s.value
    vms[name]=vm
    config["vms"]=vms
    set_config(config)
def getStoredVM(name:str)->tuple[Szerver,int]:
    config=get_config()
    vms=config.get("vms",dict())
    vm=vms.get(name,dict())
    id=vm.get("id",None)
    server=vm.get("server",None)
    if server!=None: server=Szerver(server)
    return (server,id)
def listAllVMs():
    config=get_config()
    vms:dict=config.get("vms",dict())
    for name,data in vms.items():
        print(f"{name}: {data.get('server','NOT FOUND')}, {data.get('id','NOT FOUND')}")
def removeSavedVM(name:str):
    config=get_config()
    vms:dict=config.get("vms",dict())
    rt=vms.pop(name,None)
    config["vms"]=vms
    set_config(config)
    return rt
def getNumOfNamesVMs()->int:
    config=get_config()
    vms:dict=config.get("vms",dict())
    return len(vms.items())
def removeAllNamedVMs():
    config=get_config()
    vms:dict=config.get("vms",dict())
    vms.clear()
    config["vms"]=vms
    set_config(config)
def storeCreds(user:int):
    config=get_config()
    config["username"]=user
    set_config(config)
def getCreds()->str:
    config=get_config()
    return config.get("username",None)
    
@app.command()
def wipe(
    scope:ScopeOption=typer.Argument(None),
    force:bool=typer.Option(False,"--force","-f",help="No confirmation")
):
    if scope==ScopeOption.all:
        if force or typer.confirm(f"Are you sure you want to delete EVERYTHING? This includes every saved VPS and auth credentials!"):
            set_config(dict())
    if scope==ScopeOption.auth:
        if force or typer.confirm(f"Are you sure you want to delete auth credentials? This includes the password too."):
            try:
                keyring.delete_password(SERVICE_NAME, str(getCreds()))
            except Exception:
                print("Error deleting saved password!")
            storeCreds(None)
    if scope==ScopeOption.vps:
        if force or typer.confirm(f"Are you sure you want to EVERY saved VPS?"):
            removeAllNamedVMs()
@app.command()
def auth(
    username:int=typer.Argument(None, help="@ előtti szám!"),
):
    jelszo = typer.prompt(f"Add meg a jelszót a(z) {username} fiókhoz", hide_input=True)
    try :
        keyring.set_password(SERVICE_NAME, str(username), str(jelszo))
    except Exception as e:
        print("Hiba történt a tárolás során!")
        return
    storeCreds(username)
@app.command()
def rm(
    name:str=typer.Argument(None,help="Törölni kívánt vm neve"),
    all: bool = typer.Option(False, "--all", "-a", help="Az összes mentett gép törlése"),
    force: bool = typer.Option(False, "--force", "-f", help="Megerősítő kérdés kihagyása")
):
    if all:
        num=getNumOfNamesVMs()
        if num!=0:
            if force or typer.confirm(f"Biztos törölni akarod mindet ({num})?"):
                removeAllNamedVMs()
    if not all:
        if removeSavedVM(name)==None:
            print("Sikertelen, nem található")
@app.command()
def ls():
    listAllVMs()
@app.command()
def store(
    name:str=typer.Argument(None,help="A menteni kívánt gép neve"),
    szerver: Szerver = typer.Argument(),
    id: int = typer.Argument(help="A gép azonosítója")
):
    storeNamedVM(name, szerver, id)
def parseVM(name:str, backup_server:Szerver, backup_id:int)->(tuple[Szerver,int,bool]|None):
    szerver=backup_server
    id=backup_id
    if name:
        szerver_t,id_t=getStoredVM(name)
        if not szerver_t or not id_t:
            print("Mentett VM adatok nem találhatóak!")
        else:
            print("Mentett vm adatainak betöltése...")
            print(f"Szerver: {szerver_t.value}, id: {id_t}")
            return szerver_t,id_t,True
    if backup_server and backup_id:
        return backup_server,backup_id,True
    else:
        print("Hibás argumentumok, sikertelen!")
        return None,None,False
def generateWebContext(s:Szerver):
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) Gecko/20100101 Firefox/156.0"
        )
        page = context.new_page()
        origin_url=f"https://{s.value}.cloud.bme.hu"
        print(f"Opening: {origin_url}")
        page.goto(origin_url+"/dashboard/")
        page.get_by_alt_text("Click Here!").click()
        page.wait_for_url("**/Authn/**")
        print("Authenticating...")
        username=str(getCreds())
        if username==None:
            print("Nincs eltárolva felhasználó! Tárolj el az auth parancssal!")
            browser.close()
            return -1
        page.fill("[name='j_username']", username)
        passwd=keyring.get_password(SERVICE_NAME, username)
        if passwd==None:
            print("Nem sikerült a jelszót kinyerni! Autentikálj újra az auth parancssal.")
            browser.close()
            return -1
        page.fill("[name='j_password']", passwd)
        page.click('[id="login-submit-button"]')
        page.wait_for_url("**/dashboard/**")
        return context.cookies, page.content()

def fetch_cookies(s:Szerver)->dict:
    print("Gathering cookies...")
    cookies = generateWebContext(s)[0]
    session_cookies = {c['name']: c['value'] for c in cookies}
    if not session_cookies['csrftoken']:
        print("Error: csrftoken not found")
        return None
    if not session_cookies['csessid5931']:
        print("Error: csessid5931 not found!")
        print(session_cookies.keys)
    return session_cookies
def fetchVPSsFromServer(s:Szerver)->list[tuple[int,str,Szerver]]:
    html=generateWebContext(s)[1]
    vms=re.findall(r'<a href="/dashboard/vm/(\d+)/" class="list-group-item.*?</i>\s*(.*?)\s*</span>',html,flags=re.DOTALL)
    for i in range(len(vms)): vms[i]=(int(vms[i][0]),vms[i][1],s)
    return vms
def perfom_op(s:Szerver, id:int, force_fetch:bool=False, retries:int=0, op_code:str=""):
    print("Performing operation: "+op_code)
    if retries>=MAXIMUM_ATTEMPTS:
        print("Something went really wrong (rec_depth exceeded), aborting...")
        return
    if force_fetch: cookies=None
    else:
        print("Retrieving cookies...")
        cookies=retrieveCookies(s)
        if cookies==None: print("Cookies not found!")
    if cookies==None:
        print("Fetching...")
        cookies=fetch_cookies(s)
        if cookies==None:
            print("Fetch failed! Retrying...")
            perfom_op(s,id,True,retries=retries+1,op_code=op_code)
            return
        if cookies==-1:
            print("Auth failed")
            return
        storeCookies(s,cookies)
    result=op_post(cookies, s, id,op_code=op_code)
    match (result):
        case 200:
            print("Successful!")
        case 404:
            print("Machine not found! (404)")
        case 403:
            print("Machine not found! (403)")
        case 99:
            print("Invalid cookies!")
            perfom_op(s,id,True,retries=retries+1,op_code=op_code)
def op_post(session_cookies:dict, s:Szerver, id:int, op_code:str):
    origin_url=f"https://{s.value}.cloud.bme.hu/dashboard/vm/{id}/"
    headers = {
        "X-CSRFToken": session_cookies['csrftoken'],
        "Referer": origin_url
    }
    print("Performing operation: "+origin_url+"op/"+op_code+"/")
    response=requests.post(origin_url+"op/"+op_code+"/",headers=headers,cookies=session_cookies)
    if response.text.find("CSRF verification failed")!=-1: return 99
    return response.status_code

@app.command()
def fetch(
    server:Szerver=typer.Option(None,"--szerver","-s")
):
    if server!=None:
        print(f"Fetching VPS' from {server.value}")
        vpss=fetchVPSsFromServer(server)
    else:
        vpss=[]
        for s in Szerver:
            print(f"Fetching VPS' from {s.value}")
            fetched=fetchVPSsFromServer(s)
            vpss.extend(fetched)
            print(f"Fetched {len(fetched)} VPS")
    for vps in vpss:
        if typer.confirm(f"Store VPS {vps[2].value}:{vps[0]} ({vps[1]})?"):
            name=typer.prompt(f"Enter name or leave empty for default name ({vps[1]})",default="",show_default=False)
            if name=="": name=vps[1]
            storeNamedVM(name,vps[2],vps[0])

@app.command()
def do(
    op_code:Operation=typer.Argument(...,help="Végezni kívánt operáció"),
    name:str=typer.Argument(None, help="A VM lementett szerver neve"),
    szerver: Szerver = typer.Option(None, "--szerver", "-s"),
    id: int = typer.Option(None, "--id", "-i", help="A gép azonosítója"),
    force_fetch: bool = typer.Option(False, "--force-fetch", "-f", help="Mindenképp fetcheli a cookie-kat")
):
    szerver_t,id_t,success=parseVM(name,szerver,id)
    if not success: return
    perfom_op(szerver_t,id_t,force_fetch,0,op_code.value)