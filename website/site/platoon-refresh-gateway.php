<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
function respond(int $code,array $body): never {http_response_code($code);echo json_encode($body);exit;}
if (!in_array($_SERVER['HTTP_HOST']??'', ['bf4playerstats.com','www.bf4playerstats.com'],true) || empty($_SERVER['HTTPS']) || $_SERVER['HTTPS']==='off') respond(403,['error'=>'https_required']);
session_name('BF4PS_PLATOON_REFRESH');session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Strict']);session_start();
if ($_SERVER['REQUEST_METHOD']==='GET') {if(empty($_SESSION['csrf']))$_SESSION['csrf']=bin2hex(random_bytes(32));respond(200,['csrf'=>$_SESSION['csrf']]);}
if ($_SERVER['REQUEST_METHOD']!=='POST')respond(405,['error'=>'method']);
if(!in_array($_SERVER['HTTP_ORIGIN']??'', ['https://bf4playerstats.com','https://www.bf4playerstats.com'],true))respond(403,['error'=>'origin']);
if(($_SERVER['HTTP_SEC_FETCH_SITE']??'same-origin')!=='same-origin')respond(403,['error'=>'fetch_site']);
if(empty($_SESSION['csrf'])||!hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_BF4PS_CSRF']??''))respond(403,['error'=>'csrf']);
if(strtolower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'')[0]))!=='application/json')respond(415,['error'=>'content_type']);
if((int)($_SERVER['CONTENT_LENGTH']??0)>1024)respond(413,['error'=>'too_large']);
$body=file_get_contents('php://input',false,null,0,1025);$data=json_decode($body,true);
if(!is_array($data)||array_keys($data)!==['platoon_id']||!is_string($data['platoon_id'])||!preg_match('/^[1-9][0-9]{0,18}$/',$data['platoon_id']))respond(400,['error'=>'invalid_request']);
$ip=$_SERVER['REMOTE_ADDR']??'';if(!filter_var($ip,FILTER_VALIDATE_IP))respond(403,['error'=>'client_ip']);
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
$dir='/var/lib/bf4ps-platoon-submissions';if(!is_dir($dir)||!is_writable($dir))respond(503,['error'=>'limiter_unavailable']);
$file=$dir.'/refresh-'.hash('sha256',$ip).'.json';$handle=fopen($file,'c+');if(!$handle||!flock($handle,LOCK_EX))respond(503,['error'=>'limiter_unavailable']);
$times=json_decode(stream_get_contents($handle),true);if(!is_array($times))$times=[];$now=time();$times=array_values(array_filter($times,fn($t)=>is_int($t)&&$t>$now-3600));
if(count($times)>=10){flock($handle,LOCK_UN);fclose($handle);header('Retry-After: 3600');respond(429,['error'=>'rate_limited']);}
$times[]=$now;ftruncate($handle,0);rewind($handle);fwrite($handle,json_encode($times));fflush($handle);flock($handle,LOCK_UN);fclose($handle);
}
session_write_close();
$data['lan_bypass']=$exempt;
$ch=curl_init('http://127.0.0.1:8792/refresh-platoon');curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode($data),CURLOPT_HTTPHEADER=>['Content-Type: application/json'],CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>22,CURLOPT_CONNECTTIMEOUT=>2]);$result=curl_exec($ch);$code=curl_getinfo($ch,CURLINFO_HTTP_CODE);curl_close($ch);
if(!is_string($result)||$code<100||$code>599)respond(503,['error'=>'backend_unavailable']);http_response_code($code);echo $result;
