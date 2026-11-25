<?php
// 記事サイト（guide.clarie.jp）の相談フォームの受け口。
// 1. 入力を確かめる  2. 公開されない場所（~/inquiries/guide.jsonl）に記録する  3. 担当にメールで知らせる
// 記録はサーバーのホーム直下（public_html の外）に置くので、Webからは見えず、デプロイ（rsync --delete）でも消えない。
// このファイルはリポジトリ（公開）に入るので、ここにはパスワードや個人情報を書かない。

header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex');
mb_language('Japanese');
mb_internal_encoding('UTF-8');

const TO = 'info@imp-corp.com';           // 受け先（site.yaml の inquiry_to と合わせる）
const FROM = 'noreply@guide.clarie.jp';

function out($a, $code = 200) { http_response_code($code); echo json_encode($a, JSON_UNESCAPED_UNICODE); exit; }
function v($k, $max) { $s = trim((string)($_POST[$k] ?? '')); $s = preg_replace('/[\x00-\x09\x0B-\x1F\x7F]/u', '', $s); return mb_substr($s, 0, $max); }

if ($_SERVER['REQUEST_METHOD'] !== 'POST') out(['ok' => false, 'error' => 'POST only'], 405);

$home = dirname(__DIR__, 3);
$dir = $home . '/inquiries';

// 動作確認用（送信も記録もしない）：dry=1
if (($_POST['dry'] ?? '') === '1') {
  out(['ok' => true, 'dry' => true, 'php' => PHP_VERSION, 'mail' => function_exists('mb_send_mail'),
       'store' => (is_dir($dir) ? is_writable($dir) : is_writable($home))]);
}

// 機械の送信よけ（人には見えない欄に何か入っていたら、受け付けたふりをして捨てる）
if (v('website', 200) !== '') out(['ok' => true]);

$f = [
  'kind' => v('kind', 40), 'pref' => v('pref', 10), 'city' => v('city', 60), 'madori' => v('madori', 20), 'when' => v('when', 30),
  'name' => v('name', 60), 'tel' => v('tel', 30), 'email' => v('email', 120), 'reply' => v('reply', 20), 'memo' => v('memo', 2000),
  'from' => v('from', 300),
];
if ($f['city'] === '' || $f['name'] === '') out(['ok' => false, 'error' => '市区町村とお名前を入れてください']);
if ($f['tel'] === '' && $f['email'] === '') out(['ok' => false, 'error' => 'お電話番号かメールアドレスのどちらかを入れてください']);
if ($f['email'] !== '' && !filter_var($f['email'], FILTER_VALIDATE_EMAIL)) out(['ok' => false, 'error' => 'メールアドレスの形が正しくありません']);
if ($f['tel'] !== '' && !preg_match('/^[0-9０-９\-－ ()（）+]{10,20}$/u', $f['tel'])) out(['ok' => false, 'error' => 'お電話番号の形が正しくありません']);
if (($_POST['agree'] ?? '') !== '1') out(['ok' => false, 'error' => '同意のチェックを入れてください']);

if (!is_dir($dir)) @mkdir($dir, 0700, true);

// 同じ人の連続送信を抑える（1時間に5回まで）。IPは記録せず、ハッシュだけを数える
$key = hash('sha256', ($_SERVER['REMOTE_ADDR'] ?? '') . date('YmdH'));
$rl = $dir . '/.rate';
$hits = [];
if (is_file($rl)) $hits = json_decode((string)@file_get_contents($rl), true) ?: [];
$hits = array_filter($hits, fn($t) => $t > time() - 3600, ARRAY_FILTER_USE_BOTH);
$mine = array_filter($hits, fn($t, $k) => strncmp($k, $key, strlen($key)) === 0, ARRAY_FILTER_USE_BOTH);
if (count($mine) >= 5) out(['ok' => false, 'error' => '送信が続いています。お手数ですがお電話でご連絡ください']);
$hits[$key . '_' . microtime(true)] = time();
@file_put_contents($rl, json_encode($hits), LOCK_EX);

$now = new DateTime('now', new DateTimeZone('Asia/Tokyo'));
$id = 'G' . $now->format('ymdHis') . substr(bin2hex(random_bytes(2)), 0, 3);
$rec = ['id' => $id, 'date' => $now->format('Y-m-d'), 'time' => $now->format('H:i')] + $f;
$stored = @file_put_contents($dir . '/guide.jsonl', json_encode($rec, JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND | LOCK_EX) !== false;
@chmod($dir . '/guide.jsonl', 0600);

$body = "記事サイト（guide.clarie.jp）の相談フォームから、ご相談が届きました。\n\n"
  . "受付番号：{$id}\n受付日時：{$rec['date']} {$rec['time']}\n\n"
  . "ご相談の内容：{$f['kind']}\n地域：{$f['pref']} {$f['city']}\n間取り：{$f['madori']}\n時期：{$f['when']}\n\n"
  . "お名前：{$f['name']}\nお電話：{$f['tel']}\nメール：{$f['email']}\nご連絡の方法：{$f['reply']}\n\n"
  . "気になっていること：\n{$f['memo']}\n\n"
  . "読んでいたページ：{$f['from']}\n";
$headers = 'From: ' . mb_encode_mimeheader('クラリエ 記事サイト') . ' <' . FROM . '>';
if ($f['email'] !== '') $headers .= "\r\nReply-To: " . $f['email'];
$sent = @mb_send_mail(TO, '【クラリエ】記事サイトからご相談（' . $f['pref'] . ' ' . mb_substr($f['city'], 0, 20) . '）', $body, $headers, '-f' . FROM);

if (!$stored && !$sent) out(['ok' => false, 'error' => '送信できませんでした。お手数ですがお電話でご連絡ください'], 500);
out(['ok' => true, 'id' => $id]);
