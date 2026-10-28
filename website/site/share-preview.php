<?php
declare(strict_types=1);
// Render the existing static page with server-side metadata for link unfurlers.
$kind = $_GET['kind'] ?? '';
$id = $_GET['id'] ?? '';
if (!in_array($kind, ['soldier', 'platoon'], true) || !is_string($id) || !preg_match('/^[1-9][0-9]{0,18}$/D', $id)) {
    http_response_code(400); exit('Invalid preview request');
}
$root = __DIR__;
$page = $kind === 'soldier' ? 'soldier.html' : 'platoons.html';
$html = file_get_contents($root . '/' . $page);
if ($html === false) { http_response_code(503); exit('Page unavailable'); }
$title = $kind === 'soldier' ? 'BF4 Player Stats — Soldier Dossier' : 'BF4 Platoon Stats — Platoons';
$description = $kind === 'soldier' ? 'Explore Battlefield 4 soldier statistics, weapons, vehicles, and known player aliases.' : 'Battlefield 4 official Battlelog platoons, membership, and community statistics.';
$image = 'https://bf4playerstats.com/og-preview.png';
if ($kind === 'soldier') {
    $url = 'http://127.0.0.1:8765/soldier-detail?id=' . rawurlencode($id);
    $context = stream_context_create(['http' => ['timeout' => 5, 'ignore_errors' => true]]);
    $raw = @file_get_contents($url, false, $context);
    $soldier = is_string($raw) ? (json_decode($raw, true)['soldier'] ?? null) : null;
    if (is_array($soldier) && isset($soldier['current_name'])) {
        $name = (string)$soldier['current_name'];
        $platforms = ['pc' => 'PC', 'xboxone' => 'Xbox One', 'xbox' => 'Xbox One', 'ps4' => 'PlayStation', 'ps3' => 'PlayStation'];
        $platform = $platforms[$soldier['platform'] ?? ''] ?? (string)($soldier['platform'] ?? 'BF4');
        $title = 'BF4 Player Stats — ' . $name;
        $description = $name . ' (' . $platform . ') — Battlefield 4 soldier statistics, weapons, vehicles, and aliases.';
    }
} else {
    // Small, periodically refreshed projection of the existing public export.
    $raw = @file_get_contents($root . '/platoon-preview-index.json');
    $index = is_string($raw) ? json_decode($raw, true) : null;
    $p = is_array($index) ? ($index[$id] ?? null) : null;
    if (is_array($p)) {
        $name = (string)($p['name'] ?? 'Platoon');
        $tag = trim((string)($p['tag'] ?? ''));
        $members = (int)($p['members'] ?? 0);
        $title = 'BF4 Platoon Stats — ' . $name;
        $description = ($tag !== '' ? '[' . $tag . '] · ' : '') . $members . ' official members · Battlefield 4 platoon roster and community statistics.';
        // Only publish cached local emblems; never use an arbitrary external URL.
        $emblem = (string)($p['emblem'] ?? '');
        if (preg_match('~^/assets/platoon-previews/[0-9]+-[a-f0-9]{16}-v2\.png$~D', $emblem) && is_file($root . $emblem)) {
            $image = 'https://bf4playerstats.com' . $emblem;
        }
    }
}
$canonical = 'https://bf4playerstats.com/' . $page . '?id=' . rawurlencode($id);
$escape = static fn(string $s): string => htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
// Replace generic metadata in the first HEAD, leaving the existing page and JS intact.
$html = preg_replace('~<meta\s+(?:name|property)="(?:description|og:[^"]+|twitter:[^"]+)"[^>]*>~i', '', $html);
$html = preg_replace('~<title>.*?</title>~is', '', $html, 1);
$meta = '<title>' . $escape($title) . '</title>' . "\n";
foreach (['description' => $description, 'twitter:card' => 'summary_large_image', 'twitter:title' => $title, 'twitter:description' => $description, 'twitter:image' => $image] as $key => $value) {
    $meta .= '<meta name="' . $escape($key) . '" content="' . $escape($value) . '">' . "\n";
}
foreach (['og:type' => 'website', 'og:site_name' => ($kind === 'platoon' ? 'BF4 Platoon Stats' : 'BF4 Player Stats'), 'og:title' => $title, 'og:description' => $description, 'og:url' => $canonical, 'og:image' => $image, 'og:image:alt' => $title] as $key => $value) {
    $meta .= '<meta property="' . $escape($key) . '" content="' . $escape($value) . '">' . "\n";
}
$html = preg_replace('~</head>~i', $meta . '</head>', $html, 1);
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-cache, must-revalidate');
echo $html;
