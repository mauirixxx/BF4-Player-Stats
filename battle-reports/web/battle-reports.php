<?php
declare(strict_types=1);
header('X-Content-Type-Options: nosniff');
function h($v):string{return htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
function fmtdate($v):string{return $v?gmdate('M j, Y H:i', (int)$v).' UTC':'Unknown';}
function num($v):string{return number_format((float)($v??0));}
$names=['1'=>'PC','32'=>'PlayStation','64'=>'Xbox'];
$db=pg_connect('dbname=bf4_battle_reports user=www-data');
if(!$db){http_response_code(503);exit('Database unavailable');}
$p=(string)($_GET['platform']??'all');if($p!=='all'&&!isset($names[$p]))$p='all';
$id=(string)($_GET['report']??'');if(!preg_match('/^[0-9]{1,19}$/',$id))$id='';
$person=(string)($_GET['persona']??'');if(!preg_match('/^[0-9]{1,19}$/',$person))$person='';
$page=max(1,min(100,(int)($_GET['page']??1)));
$filter=$p==='all'?'':' AND r.platform=$1';
$report=null;$players=[];$teams=[];$list=[];$stats=[];
if($id!==''){
 $res=pg_query_params($db,"SELECT r.platform,r.battlelog_report_id,d.report_json::text AS payload FROM battle_reports r JOIN battle_report_details d ON d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id WHERE r.battlelog_report_id=$1".($p==='all'?'':' AND r.platform=$2')." LIMIT 1",$p==='all'?[$id]:[$id,$p]);
 $report=pg_fetch_assoc($res)?:null;
 if($report){
  $payload=json_decode($report['payload'],true)?:[];
  $teams=array_values($payload['teams']??[]);
  $players=array_values($payload['players']??[]);
  usort($players,fn($a,$b)=>(int)($b['kills']??0)<=>(int)($a['kills']??0));
 }
}else{
 $stats=pg_fetch_all(pg_query($db,"SELECT p.platform, (SELECT count(*) FROM battle_report_raw x WHERE x.platform=p.platform) archived,(SELECT count(*) FROM history_discoveries x WHERE x.platform=p.platform) discovered,(SELECT count(*) FROM battle_report_fetch_log x WHERE x.platform=p.platform AND x.outcome <> 'ok') failed_attempts FROM (VALUES (1),(32),(64)) p(platform)"))?:[];
 $params=[];$where=' WHERE 1=1';
 if($p!=='all'){$params[]=$p;$where.=' AND r.platform=$'.count($params);}
 if($person!==''){$params[]=$person;$where.=' AND EXISTS(SELECT 1 FROM report_players rp JOIN players pl ON pl.id=rp.player_id WHERE rp.report_id=r.id AND pl.persona_id=$'.count($params).')';}
 $params[]=30;$lim='$'.count($params);$params[]=($page-1)*30;$off='$'.count($params);
 $sql="SELECT r.platform,r.battlelog_report_id,r.report_timestamp,s.current_name,(SELECT count(*) FROM report_players rp WHERE rp.report_id=r.id) player_count,d.report_json->'gameServer'->>'map' map_code,d.report_json->>'gameMode' mode,d.report_json->>'duration' duration FROM battle_reports r JOIN servers s ON s.id=r.server_id JOIN battle_report_details d ON d.platform=r.platform AND d.battlelog_report_id=r.battlelog_report_id".$where." ORDER BY r.report_timestamp DESC LIMIT $lim OFFSET $off";
 $res=pg_query_params($db,$sql,$params);$list=$res?pg_fetch_all($res)?:[]:[];
}
function urlq(array $changes):string{return '?'.http_build_query(array_merge($_GET,$changes));}
?><!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BF4 Battle Reports Archive</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0c121b;color:#e6edf7;font:15px/1.55 system-ui,Arial,sans-serif}a{color:#88caff;text-decoration:none}a:hover{text-decoration:underline}.wrap{max-width:1280px;margin:auto;padding:25px 20px 70px}.top{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;align-items:center}.brand{font-weight:900;font-size:25px;letter-spacing:.03em}.brand span{color:#ffad55}.sub{color:#9eb0c5}nav{display:flex;gap:16px;flex-wrap:wrap}.hero{padding:30px 0 16px}h1{font-size:clamp(26px,4vw,40px);line-height:1.15;margin:5px 0 10px}h2{font-size:20px;margin:0 0 15px}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:24px 0}.stat,.panel{background:#152232;border:1px solid #2b4056;border-radius:12px;padding:18px}.stat strong{display:block;font-size:29px;color:#f6aa59}.stat small{display:block;color:#a7b9cc}.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:22px 0}label{display:flex;flex-direction:column;gap:5px;color:#bacbda}select,input,button{background:#1c2b3b;border:1px solid #415a72;border-radius:8px;color:#fff;padding:10px 12px;font:inherit}input{min-width:250px}button{background:#f4a24c;color:#101923;font-weight:800;border:0;cursor:pointer}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:720px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #2a3b4d}th{color:#9cb0c6;font-size:12px;text-transform:uppercase;letter-spacing:.06em}tr:hover td{background:#1b2b3d}.pill{display:inline-block;padding:3px 9px;border-radius:30px;background:#273b51;color:#c8e0f4;font-size:12px}.pc{border-left:3px solid #e88c39}.ps{border-left:3px solid #5b8cff}.xb{border-left:3px solid #4bbb6b}.meta{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.meta .pill{font-size:14px;padding:8px 12px}.teams{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:20px 0}.team{background:#17283a;border:1px solid #354d66;border-radius:10px;padding:18px}.team strong{font-size:22px}.win{color:#76d6a3}.footer{margin-top:30px;color:#8ca2b8;font-size:13px}.paging{display:flex;gap:18px;margin:20px 0}@media(max-width:600px){.stats{grid-template-columns:1fr}.wrap{padding:16px}.stat strong{font-size:24px}}
</style></head><body><div class="wrap"><header class="top"><div class="brand">BF4 <span>BATTLE REPORTS</span><div class="sub" style="font-size:12px;font-weight:400">Independent archived match explorer</div></div><nav><a href="battle-reports.php">Archive</a><a href="shared-reports.php">Shared-player search</a></nav></header>
<?php if($report): ?>
<div class="hero"><a href="battle-reports.php">← All archived matches</a><h1><?=h($payload['gameServer']['name']??'Battle report')?></h1><div class="sub"><?=h(fmtdate($payload['createdAt']??null))?></div></div>
<div class="meta"><span class="pill"><?=h($names[$report['platform']]??$report['platform'])?></span><span class="pill">Map: <?=h($payload['gameServer']['map']??'Unknown')?></span><span class="pill">Mode: <?=h($payload['gameMode']??'Unknown')?></span><span class="pill">Duration: <?=h(gmdate('H:i:s',(int)($payload['duration']??0)))?></span><span class="pill"><?=count($players)?> players</span></div>
<div class="teams"><?php foreach($teams as $t): ?><div class="team"><div class="sub">TEAM <?=h($t['id']??'')?></div><strong><?=h($t['name']??'Team')?></strong> <?php if(!empty($t['isWinner'])):?><span class="win">WINNER</span><?php endif;?><div>Score: <?=num($t['score']??0)?></div></div><?php endforeach;?></div>
<div class="panel"><h2>Match scoreboard</h2><div class="tablewrap"><table><thead><tr><th>Player</th><th>Team</th><th>Kills</th><th>Deaths</th><th>K/D</th><th>Score</th><th>Accuracy</th><th>Revives</th></tr></thead><tbody>
<?php foreach($players as $pl):$pid=(string)($pl['personaId']??'');$kills=(int)($pl['kills']??0);$deaths=(int)($pl['deaths']??0);?><tr><td><a href="battle-reports.php?persona=<?=h(rawurlencode($pid))?>"><?=h($pl['persona']['personaName']??$pl['user']['username']??$pid)?></a><div class="sub" style="font-size:11px"><?=h($pid)?></div></td><td><?=h($pl['team']??'—')?></td><td><?=num($kills)?></td><td><?=num($deaths)?></td><td><?=h($deaths?number_format($kills/$deaths,2):($kills?'∞':'0.00'))?></td><td><?=num($pl['combatScore']??0)?></td><td><?=isset($pl['accuracy'])?h(number_format((float)$pl['accuracy']*100,1)).'%':'—'?></td><td><?=num($pl['revives']??0)?></td></tr><?php endforeach;?></tbody></table></div></div>
<div class="footer">Archived locally; no live Battlelog requests. Original full JSON is preserved in PostgreSQL. Report ID: <?=h($report['battlelog_report_id'])?>.</div>
<?php elseif($id!==''):?><div class="hero"><h1>Report not found</h1><p class="sub">This report is not present in the local archive.</p><a href="battle-reports.php">Back to archive</a></div>
<?php else:?>
<div class="hero"><h1>Every match we've rescued.</h1><p class="sub">Explore locally archived Battlefield 4 rounds across PC, PlayStation, and Xbox — even when Battlelog returns null.</p></div>
<div class="stats"><?php foreach($stats as $s):?><div class="stat <?=($s['platform']==1?'pc':($s['platform']==32?'ps':'xb'))?>"><small><?=h($names[$s['platform']]??$s['platform'])?></small><strong><?=num($s['archived'])?> archived</strong><small><?=num($s['discovered'])?> discovered · <?=num($s['failed_attempts'])?> logged failed attempts</small></div><?php endforeach;?></div>
<form class="filters" method="get"><label>Platform<select name="platform"><option value="all">All platforms</option><?php foreach($names as $key=>$name):?><option value="<?=h($key)?>" <?=$p===$key?'selected':''?>><?=h($name)?></option><?php endforeach;?></select></label><label>Persona ID<input name="persona" value="<?=h($person)?>" placeholder="Optional player persona ID"></label><button type="submit">Explore reports</button></form>
<div class="panel"><h2>Archived battle reports</h2><div class="tablewrap"><table><thead><tr><th>Report date (UTC)</th><th>Platform</th><th>Server</th><th>Map</th><th>Mode</th><th>Players</th><th>Report</th></tr></thead><tbody>
<?php foreach($list as $r):?><tr><td><?=h($r['report_timestamp'])?></td><td><span class="pill"><?=h($names[$r['platform']]??$r['platform'])?></span></td><td><?=h($r['current_name'])?></td><td><?=h($r['map_code']??'—')?></td><td><?=h($r['mode']??'—')?></td><td><?=num($r['player_count'])?></td><td><a href="battle-reports.php?report=<?=h($r['battlelog_report_id'])?>&platform=<?=h($r['platform'])?>">View scoreboard →</a></td></tr><?php endforeach;?></tbody></table></div>
<?php if(!$list):?><p class="sub">No archived reports match these filters.</p><?php endif;?></div><div class="paging"><?php if($page>1):?><a href="<?=h(urlq(['page'=>$page-1]))?>">← Previous</a><?php endif;?><?php if(count($list)===30):?><a href="<?=h(urlq(['page'=>$page+1]))?>">Next →</a><?php endif;?></div><div class="footer">Report dates are Battlelog's original timestamps. Server names reflect the latest stored name. Failed-attempt counts reflect only attempts recorded since diagnostic logging was enabled.</div>
<?php endif;?></div></body></html>
