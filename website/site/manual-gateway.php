<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function answer(int $code, array $data): never { http_response_code($code); echo json_encode($data); exit; }
function config(): array {
  $v=[];
  foreach (file('/etc/bf4ps-website/manual-api.env', FILE_IGNORE_NEW_LINES|FILE_SKIP_EMPTY_LINES) ?: [] as $line) {
    if (preg_match('/^([A-Z0-9_]+)=(.*)$/', $line, $m)) $v[$m[1]]=trim($m[2], " \"'");
  }
  return $v;
}
$origin='https://bf4playerstats.com';
$host=strtolower($_SERVER['HTTP_HOST'] ?? '');
if (!in_array($host,['bf4playerstats.com','www.bf4playerstats.com'],true)) answer(403,['error'=>'host']);
$secure=(!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS']!=='off');
if (!$secure) answer(403,['error'=>'https_required']);
session_name('BF4PS_MANUAL');
session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']);
session_start();
if ($_SERVER['REQUEST_METHOD']==='GET') {
  if (!isset($_SESSION['csrf'])) $_SESSION['csrf']=bin2hex(random_bytes(32));
  answer(200,['csrf'=>$_SESSION['csrf']]);
}
if ($_SERVER['REQUEST_METHOD']!=='POST') answer(405,['error'=>'method']);
$reqOrigin=$_SERVER['HTTP_ORIGIN']??'';
if (!in_array($reqOrigin,[$origin,'https://www.bf4playerstats.com'],true)) answer(403,['error'=>'origin']);
if (($_SERVER['HTTP_SEC_FETCH_SITE']??'same-origin')!=='same-origin') answer(403,['error'=>'fetch_site']);
if (!hash_equals($_SESSION['csrf']??'',$_SERVER['HTTP_X_BF4PS_CSRF']??'') || empty($_SESSION['csrf'])) answer(403,['error'=>'csrf']);
if (strtolower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'')[0]))!=='application/json') answer(415,['error'=>'content_type']);
if ((int)($_SERVER['CONTENT_LENGTH']??0)>2048) answer(413,['error'=>'too_large']);
$body=file_get_contents('php://input',false,null,0,2049);
$data=json_decode($body,true);
if (!is_array($data)||array_keys($data)!==['url','kind']||!is_string($data['url'])||!in_array($data['kind'],['add','refresh'],true)) answer(400,['error'=>'invalid_request']);
$ip=$_SERVER['REMOTE_ADDR']??'';
if (!filter_var($ip,FILTER_VALIDATE_IP)) answer(403,['error'=>'client_ip']);
$trusted=['192.168.10.0/24','192.168.200.0/25','192.168.5.0/24','192.168.21.0/24'];
function cidr(string $ip,string $range): bool {
  [$net,$bits]=explode('/',$range);
  $a=inet_pton($ip);$b=inet_pton($net);
  if ($a===false||$b===false||strlen($a)!==strlen($b)) return false;
  $n=(int)$bits;
  for ($i=0;$i<strlen($a);$i++) {
    $mask=$n>=8?255:($n<=0?0:(255<<(8-$n))&255);
    if ((ord($a[$i])&$mask)!==(ord($b[$i])&$mask)) return false;
    $n-=8;
  }
  return true;
}
$exempt=false;foreach ($trusted as $net) if (cidr($ip,$net)) {$exempt=true;break;}
if (!$exempt) {
  $file='/var/lib/bf4ps-manual/limits/'.hash('sha256',$ip).'.json';
  $f=fopen($file,'c+');if (!$f) answer(503,['error'=>'limiter_unavailable']);
  if (!flock($f,LOCK_EX)) answer(503,['error'=>'limiter_unavailable']);
  $times=json_decode(stream_get_contents($f),true);
  if (!is_array($times)) $times=[];
  $now=time();$times=array_values(array_filter($times,fn($t)=>is_int($t)&&$t>$now-3600));
  if (count($times)>=10) {flock($f,LOCK_UN);fclose($f);header('Retry-After: 3600');answer(429,['error'=>'rate_limited']);}
  $times[]=$now;ftruncate($f,0);rewind($f);fwrite($f,json_encode($times));fflush($f);flock($f,LOCK_UN);fclose($f);
}
session_write_close();
$cfg=config();
if (empty($cfg['BF4PS_MANUAL_PRIVATE_TOKEN'])) answer(503,['error'=>'not_configured']);
$ch=curl_init('http://127.0.0.1:8789/manual/request');
curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode($data),CURLOPT_HTTPHEADER=>['Content-Type: application/json','Origin: '.$origin,'X-BF4PS-Private-Token: '.$cfg['BF4PS_MANUAL_PRIVATE_TOKEN']],CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>12,CURLOPT_CONNECTTIMEOUT=>2]);
$result=curl_exec($ch);$status=curl_getinfo($ch,CURLINFO_HTTP_CODE);curl_close($ch);
if (!is_string($result)||$status<100||$status>599) answer(503,['error'=>'backend_unavailable']);
http_response_code($status);echo $result;
