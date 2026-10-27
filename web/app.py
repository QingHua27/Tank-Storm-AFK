import os,json,secrets,subprocess,time,threading,datetime
from pathlib import Path
from flask import Flask,request,session,jsonify,send_file,Response
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__,static_folder='static')
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
app.config.update(SECRET_KEY=os.environ['PANEL_SECRET'],SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12),MAX_CONTENT_LENGTH=4096)
lock=threading.Lock();failures={};cache={'at':0,'value':None}
CONTROL=os.environ.get('PANEL_CONTROL','/usr/local/sbin/tankstorm-webctl')
def valid_id(n):return n.isascii() and n.isdigit() and str(int(n))==n and 1<=int(n)<=32
def backend(*args,binary=False,input_text=None):
    result=subprocess.run(['sudo','-n',CONTROL,*args],input=input_text.encode('utf8') if input_text is not None else None,capture_output=True,timeout=40)
    if result.returncode:raise RuntimeError('二维码尚未生成或服务暂不可用' if binary else '服务暂不可用，请稍后重试')
    return result.stdout if binary else json.loads(result.stdout)
@app.before_request
def guard():
    allowed=set(os.environ.get('PANEL_HOSTS',os.environ.get('PANEL_HOST','localhost')).split(','))|{'127.0.0.1','localhost'}
    if request.host.split(':')[0] not in allowed:return jsonify(error='无效访问地址'),400
    if request.method=='POST':
        origin=request.headers.get('Origin')
        if origin and origin!=request.host_url.rstrip('/'):return jsonify(error='请求来源无效'),403
    if request.path.startswith('/api/') and request.path!='/api/login':
        if not session.get('admin'):return jsonify(error='请先登录'),401
        if request.method=='POST' and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','')):return jsonify(error='登录已过期，请刷新页面'),403
@app.after_request
def headers(response):
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return response
@app.get('/')
def home():return send_file(Path(app.root_path)/'static/index.html')
@app.post('/api/login')
def login():
    ip=request.remote_addr;now=time.time()
    with lock:
        for key in list(failures):
            if now-failures[key]['at']>600:del failures[key]
        if failures.get(ip,{}).get('count',0)>=8:return jsonify(error='尝试次数过多，请10分钟后再试'),429
        if len(failures)>2000:return jsonify(error='请求过多，请稍后再试'),429
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):return jsonify(error='请求格式无效'),400
    password=data.get('password','')
    if not isinstance(password,str) or len(password)>256:return jsonify(error='账号或密码不正确'),401
    valid=data.get('username')=='admin' and check_password_hash(os.environ['PANEL_PASSWORD_HASH'],password)
    if not valid:
        with lock:
            item=failures.setdefault(ip,{'at':now,'count':0});item['count']+=1
        return jsonify(error='账号或密码不正确'),401
    with lock:failures.pop(ip,None)
    session.clear();session['admin']=True;session['csrf']=secrets.token_urlsafe(32);session.permanent=True
    return jsonify(ok=True,csrf=session['csrf'])
@app.get('/api/session')
def current_session():return jsonify(username='admin',csrf=session['csrf'])
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/status')
def status():
    with lock:
        if time.monotonic()-cache['at']>1 or cache['value'] is None:cache.update(at=time.monotonic(),value=backend('status'))
        return jsonify(cache['value'])
@app.get('/api/accounts/<n>/logs')
def logs(n):
    if not valid_id(n):return jsonify(error='账号不存在'),404
    return jsonify(backend('logs',n))
@app.get('/api/accounts/<n>/qr')
def qr(n):
    if not valid_id(n):return jsonify(error='账号不存在'),404
    try:return Response(backend('qr',n,binary=True),mimetype='image/png')
    except RuntimeError:return jsonify(error='等待二维码生成'),404
@app.get('/api/accounts/<n>/avatar')
def account_avatar(n):
    if not valid_id(n):return jsonify(error='账号不存在'),404
    try:
        image=backend('avatar',n,binary=True)
        return Response(image,mimetype='image/png' if image.startswith(b'\x89PNG') else 'image/jpeg')
    except (RuntimeError,subprocess.TimeoutExpired):return jsonify(error='头像暂不可用'),404
@app.post('/api/accounts/<n>/<action>')
def action(n,action):
    if not valid_id(n) or action not in ('start','stop','login'):return jsonify(error='操作不存在'),404
    value=backend(action,n)
    with lock:cache['at']=0
    return jsonify(value)
@app.post('/api/accounts')
def add_account():
    value=backend('add')
    with lock:cache['at']=0
    return jsonify(value)
@app.post('/api/accounts/<n>/rename')
def rename_account(n):
    if not valid_id(n):return jsonify(error='账号不存在'),404
    data=request.get_json(silent=True)
    name=data.get('name') if isinstance(data,dict) else None
    import unicodedata
    if not isinstance(name,str) or name!=name.strip() or not 1<=len(name)<=32 or any(unicodedata.category(c).startswith('C') for c in name):return jsonify(error='请输入 1 至 32 个字符的名称'),400
    value=backend('rename',n,input_text=name)
    with lock:cache['at']=0
    return jsonify(value)
@app.post('/api/accounts/<n>/delete')
def delete_account(n):
    if not valid_id(n):return jsonify(error='账号不存在'),404
    value=backend('delete',n)
    with lock:cache['at']=0
    return jsonify(value)
@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc,subprocess.TimeoutExpired):return jsonify(error='操作仍在处理中，请稍后查看状态'),504
    from werkzeug.exceptions import HTTPException
    if isinstance(exc,HTTPException):return jsonify(error=exc.description),exc.code
    app.logger.error('request failed: %s',type(exc).__name__)
    return jsonify(error='服务暂不可用，请稍后重试'),503
