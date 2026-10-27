#!/usr/bin/python3
"""Small privileged boundary. Only fixed operations on account 1 or 2 are allowed."""
import sys, subprocess, pathlib, json, re, datetime, time, fcntl, os, shutil, pwd, uuid, urllib.parse, urllib.request, unicodedata
ROOT = pathlib.Path('/opt/tankstorm/accounts')
BACKUPS = ROOT/'.backups'
METADATA = pathlib.Path('/opt/tankstorm/panel-account-names')
TEMPLATE = pathlib.Path('/opt/tankstorm/releases/v2.0.0/unpacked/tankstorm-linux-x64')
RUNTIME = pathlib.Path('/run/tankstorm-panel')
MAX_ACCOUNTS = 32
def account_ids():
    return sorted([p.name[8:] for p in ROOT.glob('account-*') if p.is_dir() and not p.is_symlink() and re.fullmatch(r'account-[1-9][0-9]?',p.name) and int(p.name[8:])<=MAX_ACCOUNTS],key=int)
def avatar(n):
    path=ROOT/f'account-{n}'/'cookies.json'
    if path.is_symlink() or path.stat().st_size>262144:raise ValueError('invalid cookies')
    jar=json.loads(path.read_text(encoding='utf8'))
    uin=next((c.get('value','') for c in jar if c.get('name')=='uin' and c.get('domain') in ('.qq.com','qq.com')),None)
    if not isinstance(uin,str) or not re.fullmatch(r'o?[0-9]{5,12}',uin):raise ValueError('missing account')
    uin=str(int(uin.lstrip('o')))
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    req=urllib.request.Request('https://q1.qlogo.cn/g?'+urllib.parse.urlencode({'b':'qq','nk':uin,'s':'100'}),headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.build_opener(NoRedirect).open(req,timeout=6) as response:
        data=response.read(262145)
    if len(data)>262144 or not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')):raise ValueError('invalid image')
    return data
def clean_name(value):
    if not isinstance(value,str):return ''
    value=''.join(c for c in value.strip() if not unicodedata.category(c).startswith('C'))
    return value if 0<len(value)<=32 else ''
def account_name(n):
    try:
        custom=clean_name((METADATA/f'{n}.txt').read_text(encoding='utf8'))
        if custom:return custom
    except (OSError,UnicodeError):pass
    try:
        path=ROOT/f'account-{n}'/'cookies.json'
        if path.is_symlink() or path.stat().st_size>262144:return f'账号 {n}'
        jar=json.loads(path.read_text(encoding='utf8'))
        for cookie in jar:
            if re.fullmatch(r'ptnick_[0-9]+',cookie.get('name','')):
                raw=urllib.parse.unquote(cookie.get('value',''))
                if len(raw)%2==0 and re.fullmatch(r'(?:[0-9a-fA-F]{2}){2,}',raw):
                    try:raw=bytes.fromhex(raw).decode('utf8')
                    except (ValueError,UnicodeError):pass
                nick=clean_name(raw)
                if nick:return nick
    except (OSError,ValueError,TypeError,AttributeError):pass
    return f'账号 {n}'
def rename_account(n,name):
    value=clean_name(name)
    if value!=name or not value:raise ValueError('invalid name')
    METADATA.mkdir(mode=0o700,parents=True,exist_ok=True)
    tmp=METADATA/f'.{uuid.uuid4().hex}.tmp'
    try:
        tmp.write_text(value,encoding='utf8');os.chmod(tmp,0o600);os.replace(tmp,METADATA/f'{n}.txt')
    finally:tmp.unlink(missing_ok=True)
    return {'ok':True,'account':n,'name':value}
def delete_account(n):
    # Caller holds both account and creation locks. Never follow an account symlink.
    folder=ROOT/f'account-{n}'
    if n not in account_ids():raise ValueError('account missing')
    for args in [('stop',f'tankstorm-daily@{n}.timer'),('disable',f'tankstorm-daily@{n}.timer'),('stop',f'tankstorm-login@{n}.service'),('stop',f'tankstorm@{n}.service'),('disable',f'tankstorm@{n}.service')]:
        if command('systemctl',*args).returncode:raise RuntimeError('cannot stop account')
    if props(f'tankstorm@{n}.service').get('ActiveState')!='inactive' or props(f'tankstorm-login@{n}.service').get('ActiveState') not in ('inactive','failed'):
        raise RuntimeError('account did not stop')
    BACKUPS.mkdir(mode=0o700,parents=True,exist_ok=True)
    target=BACKUPS/f'account-{n}-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}'
    folder.rename(target)
    metadata=METADATA/f'{n}.txt'
    if metadata.exists():
        (target/'panel-name.txt').write_text(metadata.read_text(encoding='utf8'),encoding='utf8')
        metadata.unlink()
    return {'ok':True,'account':n}
def create_account():
    RUNTIME.mkdir(mode=0o700,exist_ok=True)
    with (RUNTIME/'add.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);ids=set(map(int,account_ids()));number=next((i for i in range(1,MAX_ACCOUNTS+1) if i not in ids),None)
        if number is None:raise ValueError('account limit reached')
        target=ROOT/f'account-{number}';stage=ROOT/f'.new-{uuid.uuid4().hex}';stage.mkdir(mode=0o700)
        try:
            user=pwd.getpwnam('tankstorm')
            shutil.copyfile(TEMPLATE/'tankstorm',stage/'tankstorm');os.chmod(stage/'tankstorm',0o750);os.chown(stage/'tankstorm',0,user.pw_gid)
            shutil.copyfile(TEMPLATE/'config.json',stage/'config.json')
            (stage/'config.local.json').write_text(json.dumps({'保持活跃':{'持续小时':0},'通知':{'pushplus_token':''}},ensure_ascii=False)+'\n')
            for filename in ('config.json','config.local.json'):
                os.chmod(stage/filename,0o600);os.chown(stage/filename,user.pw_uid,user.pw_gid)
            os.chown(stage,user.pw_uid,user.pw_gid);stage.rename(target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return {'ok':True,'account':str(number),'name':f'账号 {number}'}
def system_statistics():
    values=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));total=sum(values);idle=values[3]+values[4]
    RUNTIME.mkdir(mode=0o700,exist_ok=True);cpu=None
    with (RUNTIME/'metrics.json').open('a+') as file:
        fcntl.flock(file,fcntl.LOCK_EX);file.seek(0)
        try:previous=json.load(file)
        except ValueError:previous={}
        if total>previous.get('total',total):cpu=round(max(0,min(100,100*(1-(idle-previous['idle'])/(total-previous['total'])))),1)
        file.seek(0);file.truncate();json.dump({'total':total,'idle':idle},file)
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if ':' in line and line.split()[1].isdigit()}
    used=memory['MemTotal']-memory['MemAvailable'];disk=shutil.disk_usage('/')
    return {'cpu_percent':cpu,'cpu_cores':os.cpu_count(),'load_1m':round(os.getloadavg()[0],2),'memory_used':used,'memory_total':memory['MemTotal'],'memory_percent':round(100*used/memory['MemTotal'],1),'disk_used':disk.used,'disk_total':disk.total,'disk_percent':round(100*disk.used/disk.total,1),'uptime':int(float(pathlib.Path('/proc/uptime').read_text().split()[0]))}
def command(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=35)
def props(unit):
    result = command('systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID', '-p', 'NRestarts', '-p', 'ActiveEnterTimestampMonotonic', '-p', 'ExecMainStartTimestampMonotonic')
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
def read_lines(n):
    paths=list((ROOT/f'account-{n}'/'logs').glob('*.log'))
    if not paths:return []
    path=max(paths,key=lambda p:p.stat().st_mtime)
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-98304))
        return stream.read().decode('utf8','replace').splitlines()
def current_lines(lines,service):
    start=float(service.get('ExecMainStartTimestampMonotonic','0'))/1e6
    if not start:return []
    epoch=time.time()-time.monotonic()+start;output=[]
    for line in lines:
        try:stamp=datetime.datetime.strptime(line[:23],'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp()
        except ValueError:continue
        if stamp>=epoch-.05:output.append(line)
    return output
def phase(lines):
    value='unknown'
    for line in lines:
        if 'cookie 有效' in line or '登录完成' in line:value='verified'
        if '心跳运行中' in line or '任务执行中心跳' in line:value='online'
        if '请用手机 QQ 扫码' in line:value='scan'
        if '已扫码，请在手机上确认' in line:value='confirm'
        if '扫码确认成功' in line:value='finishing'
        if '二维码已失效' in line or '二维码已过期' in line or '扫码超时' in line:value='expired'
        if '服务器关闭连接' in line or '重新连接' in line:value='reconnecting'
    return value
def region_from_lines(lines):
    for line in reversed(lines):
        if '已解析 FlashVars' in line:
            match=re.search(r'\bregion=(0|[1-9][0-9]{0,4})(?:\s|$)',line)
            if match:return int(match.group(1))+1
    return None
def scrub(line):
    if '[DEBUG]' in line:return None
    if any(k in line for k in ('提取到的上下文','FlashVars','openid','openkey','uin=','sid=','uid=','socket 登录参数','cookie 已保存','pushplus_token')):return None
    line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line)
    line=re.sub(r'https?://\S+','[链接]',line)
    line=re.sub(r'(?:/opt/\S+|F:\\\S+)','[账号目录]',line)
    line=re.sub(r'\b\d{5,}\b','[编号]',line)
    line=re.sub(r'(?i)((?:token|secret|skey|cookie|pfkey)\s*[=:]\s*)\S+',r'\1[已隐藏]',line)
    return line[:500]
def status(n):
    data=props(f'tankstorm@{n}.service');login=props(f'tankstorm-login@{n}.service')
    state=data.get('ActiveState','unknown');lines=read_lines(n);current=phase(current_lines(lines,login if login.get('ActiveState')=='activating' else data))
    if login.get('ActiveState')=='activating':state='login';current=current if current in ('scan','confirm','finishing','expired') else 'scan'
    elif state!='active':current='expired' if login.get('ActiveState')=='failed' else 'stopped'
    since=float(data.get('ActiveEnterTimestampMonotonic','0'))/1e6
    uptime=max(0,int(time.monotonic()-since)) if state=='active' and since else 0
    folder=ROOT/f'account-{n}';done={};config={}
    qr_expires_at=None
    if current in ('scan','confirm'):
        try:
            qr_expires_at=int((folder/'qrcode.png').stat().st_mtime)+180
            if time.time()>=qr_expires_at:current='expired'
        except OSError:pass
    try:
        value=json.loads((folder/'logs/daily-state.json').read_text())
        if value.get('date')==datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d'):done=value.get('done',{})
    except (OSError,ValueError):pass
    for name in ('config.json','config.local.json'):
        try:
            value=json.loads((folder/name).read_text(encoding='utf-8-sig'));config.update(value.get('每日任务',{}).get('任务',{}))
        except (OSError,ValueError,AttributeError):pass
    selected=[k for k,v in config.items() if not k.startswith('_') and v is True]
    safe=[s for line in lines[-120:] if (s:=scrub(line))]
    return dict(id=n,name=account_name(n),region=region_from_lines(lines),state=state,phase=current,qr_expires_at=qr_expires_at,pid=int(data.get('MainPID','0')),restarts=int(data.get('NRestarts','0')),uptime=uptime,completed=sum(1 for k in selected if done.get(k,0)>0),total=len(selected),last_event=safe[-1] if safe else '暂无运行日志')
def main():
    if len(sys.argv) not in (2,3):raise ValueError('invalid command')
    action=sys.argv[1];n=sys.argv[2] if len(sys.argv)==3 else None
    if action=='status' and n is None:
        print(json.dumps({'accounts':[status(n) for n in account_ids()],'server':system_statistics(),'limits':{'max_accounts':MAX_ACCOUNTS},'server_time':int(time.time())},ensure_ascii=False));return
    if action=='add' and n is None:print(json.dumps(create_account(),ensure_ascii=False));return
    if n not in account_ids() or action not in ('start','stop','login','logs','qr','rename','delete','avatar'):raise ValueError('invalid account/action')
    if action=='avatar':sys.stdout.buffer.write(avatar(n));return
    if action=='logs':
        safe=[s for line in read_lines(n) if (s:=scrub(line))]
        print(json.dumps({'lines':safe[-100:]},ensure_ascii=False));return
    if action=='qr':
        state=status(n)
        if state['phase'] not in ('scan','confirm','finishing'):sys.exit(4)
        path=ROOT/f'account-{n}'/'qrcode.png'
        content=path.read_bytes()
        if not content.startswith(b'\x89PNG\r\n\x1a\n') or len(content)>1048576 or time.time()-path.stat().st_mtime>180:sys.exit(4)
        sys.stdout.buffer.write(content);return
    os.makedirs('/run/tankstorm-panel',mode=0o700,exist_ok=True)
    with open(f'/run/tankstorm-panel/account-{n}.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if n not in account_ids():raise ValueError('account missing')
        if action=='rename':
            value=sys.stdin.read(1025)
            if len(value)>1024:raise ValueError('name too long')
            print(json.dumps(rename_account(n,value),ensure_ascii=False));return
        if action=='delete':
            with (RUNTIME/'add.lock').open('w') as add_lock:
                fcntl.flock(add_lock,fcntl.LOCK_EX)
                print(json.dumps(delete_account(n),ensure_ascii=False));return
        if action in ('start','login'):
            enabled=command('systemctl','enable',f'tankstorm@{n}.service',f'tankstorm-daily@{n}.timer')
            if enabled.returncode:raise RuntimeError('enable failed')
            if command('systemctl','start',f'tankstorm-daily@{n}.timer').returncode:raise RuntimeError('timer failed')
        result=command('/usr/local/sbin/tankstormctl',action,n)
        if result.returncode:raise RuntimeError('service operation failed')
    print(json.dumps({'ok':True,'account':n,'action':action}))
if __name__=='__main__':
    try:main()
    except Exception:print(json.dumps({'error':'服务操作失败，请稍后重试'}));sys.exit(1)
