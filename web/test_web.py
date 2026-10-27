import os,unittest,importlib.util,tempfile,pathlib,json
from unittest.mock import patch
from werkzeug.security import generate_password_hash
os.environ['PANEL_SECRET']='test-only-session-key'
os.environ['PANEL_PASSWORD_HASH']=generate_password_hash('test-only-password')
import app as module
import control

class WebSecurityTests(unittest.TestCase):
 def setUp(self):
  self.client=module.app.test_client();module.failures.clear();module.cache.update(at=0,value=None)
 def call(self,path,method='GET',**kwargs):return self.client.open(path,method=method,base_url='https://localhost',**kwargs)
 def login(self):
  response=self.call('/api/login','POST',json={'username':'admin','password':'test-only-password'})
  self.assertEqual(response.status_code,200);return response.json['csrf']
 def test_private_routes_require_login(self):
  for path in ['/api/status','/api/session','/api/accounts/1/qr','/api/accounts/2/logs']:
   self.assertEqual(self.call(path).status_code,401)
 def test_password_validation_and_rate_limit(self):
  for _ in range(8):self.assertEqual(self.call('/api/login','POST',json={'username':'admin','password':'wrong'}).status_code,401)
  self.assertEqual(self.call('/api/login','POST',json={'username':'admin','password':'test-only-password'}).status_code,429)
 def test_session_cookie_and_logout(self):
  response=self.call('/api/login','POST',json={'username':'admin','password':'test-only-password'})
  for value in ['Secure','HttpOnly','SameSite=Strict']:self.assertIn(value,response.headers['Set-Cookie'])
  token=response.json['csrf'];self.assertEqual(self.call('/api/session').status_code,200)
  self.assertEqual(self.call('/api/logout','POST',headers={'X-CSRF-Token':token},json={}).status_code,200)
  self.assertEqual(self.call('/api/session').status_code,401)
 def test_csrf_and_cross_origin_rejected(self):
  token=self.login()
  self.assertEqual(self.call('/api/accounts/1/stop','POST',json={}).status_code,403)
  self.assertEqual(self.call('/api/accounts/1/stop','POST',headers={'X-CSRF-Token':token,'Origin':'https://evil.example'},json={}).status_code,403)
 def test_actions_stay_scoped_and_invalid_ids_rejected(self):
  token=self.login();headers={'X-CSRF-Token':token,'Origin':'https://localhost'}
  with patch.object(module,'backend',return_value={'ok':True}) as backend:
   self.assertEqual(self.call('/api/accounts/2/start','POST',headers=headers,json={}).status_code,200)
   backend.assert_called_once_with('start','2')
   self.assertEqual(self.call('/api/accounts/33/start','POST',headers=headers,json={}).status_code,404)
   self.assertEqual(self.call('/api/accounts/33/delete','POST',headers=headers,json={}).status_code,404)
 def test_rename_and_delete_require_csrf_and_validate_names(self):
  token=self.login();headers={'X-CSRF-Token':token,'Origin':'https://localhost'}
  self.assertEqual(self.call('/api/accounts/2/delete','POST',json={}).status_code,403)
  with patch.object(module,'backend',return_value={'ok':True}) as backend:
   self.assertEqual(self.call('/api/accounts/2/rename','POST',headers=headers,json={'name':'小明'}).status_code,200)
   backend.assert_called_once_with('rename','2',input_text='小明');backend.reset_mock()
   self.assertEqual(self.call('/api/accounts/2/rename','POST',headers=headers,json={'name':'a\nxxx'}).status_code,400)
   self.assertEqual(self.call('/api/accounts/2/rename','POST',headers=headers,json={'name':'x'*33}).status_code,400)
   backend.assert_not_called()
   self.assertEqual(self.call('/api/accounts/2/delete','POST',headers=headers,json={}).status_code,200)
   backend.assert_called_once_with('delete','2')
 def test_qr_private_png_and_pending(self):
  self.login()
  with patch.object(module,'backend',return_value=b'\x89PNG\r\n\x1a\n'):
   response=self.call('/api/accounts/1/qr');self.assertEqual(response.mimetype,'image/png');self.assertEqual(response.headers['Cache-Control'],'no-store')
  with patch.object(module,'backend',side_effect=RuntimeError()):self.assertEqual(self.call('/api/accounts/1/qr').status_code,404)
 def test_logs_are_not_rendered_as_markup(self):
  self.login()
  with patch.object(module,'backend',return_value={'lines':['<script>alert(1)</script>']}):
   response=self.call('/api/accounts/1/logs');self.assertEqual(response.mimetype,'application/json')
 def test_status_cache_avoids_duplicate_processes(self):
  self.login()
  with patch.object(module,'backend',return_value={'accounts':[]}) as backend:
   self.call('/api/status');self.call('/api/status');self.assertEqual(backend.call_count,1)
 def test_add_account_requires_csrf_and_dispatches_fixed_command(self):
  token=self.login()
  self.assertEqual(self.call('/api/accounts','POST',json={}).status_code,403)
  with patch.object(module,'backend',return_value={'ok':True,'account':'3'}) as backend:
   self.assertEqual(self.call('/api/accounts','POST',headers={'X-CSRF-Token':token},json={}).status_code,200)
   backend.assert_called_once_with('add')

class PresentationTests(unittest.TestCase):
 def test_region_number_matches_game_display(self):
  for raw,display in ((0,1),(2,3),(34,35),(35,36)):
   self.assertEqual(control.region_from_lines([f'已解析 FlashVars：server=host region={raw}']),display)
  self.assertIsNone(control.region_from_lines(['no game region']))
 def test_qq_nickname_and_custom_override(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=pathlib.Path(temporary);folder=root/'accounts/account-1';folder.mkdir(parents=True)
   (folder/'cookies.json').write_text(json.dumps([{'name':'ptnick_12345','value':'%E5%B0%8F%E6%98%8E'}]))
   with patch.object(control,'ROOT',root/'accounts'),patch.object(control,'METADATA',root/'metadata'):
    self.assertEqual(control.account_name('1'),'小明');control.rename_account('1','我的账号')
    self.assertEqual(control.account_name('1'),'我的账号')
    with self.assertRaises(ValueError):control.rename_account('1','bad\nname')
 def test_hex_encoded_qq_nickname(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=pathlib.Path(temporary);folder=root/'accounts/account-1';folder.mkdir(parents=True)
   (folder/'cookies.json').write_text(json.dumps([{'name':'ptnick_12345','value':'e5b08fe6988e'}]))
   with patch.object(control,'ROOT',root/'accounts'),patch.object(control,'METADATA',root/'metadata'):
    self.assertEqual(control.account_name('1'),'小明')
 def test_delete_backups_only_selected_account(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as temporary:
   root=pathlib.Path(temporary);accounts=root/'accounts';accounts.mkdir()
   for n in ('1','2'):
    folder=accounts/f'account-{n}';folder.mkdir();(folder/'cookies.json').write_text('private')
   with patch.object(control,'ROOT',accounts),patch.object(control,'BACKUPS',root/'backups'),patch.object(control,'METADATA',root/'metadata'),patch.object(control,'command',return_value=SimpleNamespace(returncode=0)),patch.object(control,'props',return_value={'ActiveState':'inactive'}):
    control.rename_account('1','名字');self.assertTrue(control.delete_account('1')['ok'])
    self.assertEqual(control.account_ids(),['2']);self.assertTrue((accounts/'account-2/cookies.json').exists())
    backups=list((root/'backups').iterdir());self.assertEqual(len(backups),1)
    self.assertEqual((backups[0]/'cookies.json').read_text(),'private');self.assertEqual((backups[0]/'panel-name.txt').read_text(),'名字')
    self.assertEqual((root/'backups').stat().st_mode & 0o777,0o700)
 def test_old_connection_evidence_is_not_current_login(self):
  import time,datetime
  tz=datetime.timezone(datetime.timedelta(hours=8))
  before=(datetime.datetime.now(tz)-datetime.timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M:%S,%f')[:23]+' 心跳运行中'
  current=(datetime.datetime.now(tz)+datetime.timedelta(milliseconds=100)).strftime('%Y-%m-%d %H:%M:%S,%f')[:23]+' 请用手机 QQ 扫码登录'
  props={'ExecMainStartTimestampMonotonic':str(int(time.monotonic()*1000000))}
  self.assertEqual(control.phase(control.current_lines([before],props)),'unknown')
  self.assertEqual(control.phase(control.current_lines([before,current],props)),'scan')
 def test_system_metrics_use_real_bounded_values(self):
  with tempfile.TemporaryDirectory() as temporary,patch.object(control,'RUNTIME',pathlib.Path(temporary)):
   first=control.system_statistics();second=control.system_statistics()
   self.assertGreater(first['memory_total'],0);self.assertGreaterEqual(first['disk_percent'],0);self.assertLessEqual(first['disk_percent'],100)
   if second['cpu_percent'] is not None:self.assertTrue(0<=second['cpu_percent']<=100)
 def test_new_account_does_not_inherit_credentials(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=pathlib.Path(temporary);accounts=root/'accounts';accounts.mkdir();template=root/'template';template.mkdir()
   (template/'tankstorm').write_bytes(b'trusted-fixture');(template/'config.json').write_text('{}')
   for n in ('1','2'):
    folder=accounts/f'account-{n}';folder.mkdir();(folder/'cookies.json').write_text('private-fixture')
   with patch.object(control,'ROOT',accounts),patch.object(control,'TEMPLATE',template),patch.object(control,'RUNTIME',root/'run'):
    result=control.create_account();self.assertEqual(result['account'],'3')
    self.assertFalse((accounts/'account-3/cookies.json').exists());self.assertFalse((accounts/'account-3/logs').exists())
    self.assertEqual((accounts/'account-1/cookies.json').read_text(),'private-fixture')
    self.assertEqual(control.account_ids(),['1','2','3'])
 def test_auth_phases_are_separate_from_engine_activity(self):
  self.assertEqual(control.phase(['cookie 有效','请用手机 QQ 扫码登录']),'scan')
  self.assertEqual(control.phase(['已扫码，请在手机上确认']),'confirm')
  self.assertEqual(control.phase(['扫码确认成功','登录完成','心跳运行中']),'online')
  self.assertEqual(control.phase(['心跳运行中','二维码已失效']),'expired')
  self.assertEqual(control.phase(['请用手机 QQ 扫码登录','扫码超时（180 秒）']),'expired')
 def test_log_credentials_and_debug_hidden(self):
  for line in ['[DEBUG] x','提取到的上下文 openkey=secret','cookie 已保存','uid=12345678','pushplus_token=secret']:
   self.assertIsNone(control.scrub(line))
  self.assertNotIn('secret',control.scrub('[WARNING] token=secret'))
 def test_account_state_and_counts_remain_independent(self):
  import datetime
  date=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
  with tempfile.TemporaryDirectory() as temporary:
   root=pathlib.Path(temporary)
   for n,count in [('1',1),('2',0)]:
    path=root/f'account-{n}';(path/'logs').mkdir(parents=True)
    (path/'config.json').write_text(json.dumps({'每日任务':{'任务':{'每日签到':True,'英雄开采':False}}}))
    (path/'logs/daily-state.json').write_text(json.dumps({'date':date,'done':{'每日签到':count}}))
   with patch.object(control,'ROOT',root),patch.object(control,'props',return_value={'ActiveState':'active','MainPID':'1'}):
    self.assertEqual(control.status('1')['completed'],1);self.assertEqual(control.status('2')['completed'],0)

if __name__=='__main__':unittest.main(verbosity=2)
