<?php
/**
 * Fahrplan-Aushang aus der lokalen App erzeugen.
 * Liest die fertig berechneten Fahrten aus der App-Datenbank (db/app-*.sqlite, nur lesend),
 * schreibt sie in das Layout von "Busfahrplan.xlsx" (Vorlage, bleibt unverändert) und speichert
 * "Busfahrplan-aktuell.xlsx" im selben Ordner. Aufruf: C:\xampp\php\php.exe fahrplan_aktualisieren.php
 */
mb_internal_encoding('UTF-8');
$dir = __DIR__;
$vorlage = $dir . DIRECTORY_SEPARATOR . 'Busfahrplan.xlsx';
$ziel = $dir . DIRECTORY_SEPARATOR . 'Busfahrplan-aktuell.xlsx';

function fail(string $m): void { fwrite(STDERR, "FEHLER: $m\n"); exit(1); }
if (!class_exists('ZipArchive')) fail('Die PHP-Erweiterung "zip" ist nicht aktiv (XAMPP: php.ini, extension=zip).');
if (!is_file($vorlage)) fail('Vorlage nicht gefunden: ' . $vorlage);

// Fahrten: zusatz-strecken.json (aus dem Xunta-Datensatz, Betreiber je Fahrt), Preise je Strecke
$jf = json_decode((string)@file_get_contents($dir . DIRECTORY_SEPARATOR . 'zusatz-strecken.json'), true);
if (!$jf) fail('zusatz-strecken.json fehlt oder ist ungültig.');
$namen = ['F' => 'FISTERRA', 'S' => 'SANTIAGO', 'C' => 'A CORUÑA', 'M' => 'MUXIA'];
$preise = ['FS' => '7,20€', 'SF' => '7,20€', 'FC' => '9,25€', 'CF' => '9,25€', 'FM' => '2,60€', 'MF' => '2,60€', 'MS' => '6,70€', 'SM' => '6,70€', 'MC' => '8,15€', 'CM' => '8,15€'];
$pj = $dir . DIRECTORY_SEPARATOR . 'preise.json';
if (is_file($pj)) { $x = json_decode((string)file_get_contents($pj), true); if (is_array($x)) $preise = $x + $preise; }
$blaetter = [
    'Fisterra' => ['FS', 'SF', 'FC', 'CF'],
    'Muxia' => ['MF', 'FM'],
    'Muxia-Santiago' => ['MS', 'SM'],
    'Muxia-A Coruña' => ['MC', 'CM'],
];

function esc(string $s): string { return htmlspecialchars($s, ENT_XML1 | ENT_QUOTES, 'UTF-8'); }
function cs(string $ref, int $st, string $text): string { return '<c r="' . $ref . '" s="' . $st . '" t="inlineStr"><is><t xml:space="preserve">' . esc($text) . '</t></is></c>'; }
function cn(string $ref, int $st, ?float $v): string { return $v === null ? '<c r="' . $ref . '" s="' . $st . '"/>' : '<c r="' . $ref . '" s="' . $st . '"><v>' . rtrim(rtrim(sprintf('%.15f', $v+1e-9), '0'), '.') . '</v></c>'; }
function frac(string $hm): float { [$h, $m] = array_map('intval', explode(':', $hm)); return ($h * 60 + $m) / 1440; }

/** Fahrten einer Strecke in die drei Spaltenpaare; jede Zeile: [Abfahrt, Ankunft, Betreiber]. */
function spalten(array $jf, string $code): array {
    $g = $jf['strecken'][$code] ?? [];
    $col = [];
    foreach (['mo-fr', 'sa', 'so'] as $i => $k) {
        $col[$i] = array_map(function ($f) { [$t, $b] = explode('|', $f); [$ab, $an] = explode('-', $t); return [$ab, $an, $b]; }, $g[$k] ?? []);
        usort($col[$i], fn($x, $y) => sprintf('%05s', $x[0]) <=> sprintf('%05s', $y[0]));
    }
    return $col;
}

$dt = fn($d) => $d ? date('d.m.Y', strtotime($d)) : '-';
$standText = 'Actualizado: ' . $dt($jf['stand'] ?? '') . '  ·  válido hasta: ' . $dt($jf['gueltig_bis'] ?? '')
    . "\n" . 'Fuente: NAP – Ministerio de Transportes, Xunta de Galicia'
    . "\n" . '(A) = Arriva - (M) = Monbus';

function blattXml(array $jf, array $codes, array $namen, array $preise, string $standText, string $kopf): string {
    $rows = ''; $merge = []; $r = 0;
    $mkRow = function (int $nr, string $cells, ?float $ht = null) { return '<row r="' . $nr . '"' . ($ht ? ' ht="' . $ht . '" customHeight="1"' : '') . '>' . $cells . '</row>'; };
    foreach ($codes as $code) {
        $col = spalten($jf, $code);
        $titel = $namen[$code[0]] . ' - ' . $namen[$code[1]];
        $p = $preise[$code] ?? ''; if ($p !== '') $titel .= ' ' . $p;
        $r++; $c = cs("A$r", 61, $titel); foreach (['B', 'C', 'D', 'E', 'F'] as $L) $c .= '<c r="' . $L . $r . '" s="61"/>'; $rows .= $mkRow($r, $c, 27); $merge[] = "A$r:F$r";
        $r++; $rows .= $mkRow($r, cs("A$r", 16, 'Lunes - Viernes') . '<c r="B' . $r . '" s="17"/>' . cs("C$r", 51, 'Sábado') . '<c r="D' . $r . '" s="52"/>' . cs("E$r", 53, 'Domingo | Festivo') . '<c r="F' . $r . '" s="54"/>', 25.5); $merge[] = "A$r:B$r"; $merge[] = "C$r:D$r"; $merge[] = "E$r:F$r";
        $r++; $c = ''; foreach (['A', 'B', 'C', 'D', 'E', 'F'] as $i => $L) $c .= cs("$L$r", $i % 2 ? 19 : 18, $i % 2 ? 'Llegada' : 'Salida'); $rows .= $mkRow($r, $c);
        $n = max(1, count($col[0]), count($col[1]), count($col[2]));
        for ($k = 0; $k < $n; $k++) {
            $r++;
            $pos = $k === 0 ? 'first' : ($k === $n - 1 ? 'last' : ($k % 2 ? 'a' : 'b'));
            $stl = ['first' => [21, 22], 'a' => [11, 13], 'b' => [25, 26], 'last' => [27, 28]][$pos];
            if ($n === 1) $stl = [21, 22];
            $c = '';
            foreach ([0, 1, 2] as $i) {
                $L1 = ['A', 'C', 'E'][$i]; $L2 = ['B', 'D', 'F'][$i];
                $z = $col[$i][$k] ?? null;
                $c .= ($z ? cs("$L1$r", $stl[0], ltrim($z[0], '0') . ' (' . $z[2][0] . ')') : cn("$L1$r", $stl[0], null)) . cn("$L2$r", $stl[1], $z ? frac($z[1]) : null);
            }
            $rows .= $mkRow($r, $c, 20.25);
        }
        $r++; $rows .= $mkRow($r, '<c r="A' . $r . '" s="62"/>', 6.75);
    }
    $r++;
    foreach (['*La responsabilidad de posibles cambios de horarios es de las líneas de autobuses*', ...explode("\n", $standText)] as $t) {
        $c = cs("A$r", 60, $t); foreach (['B', 'C', 'D', 'E', 'F'] as $L) $c .= '<c r="' . $L . $r . '" s="60"/>';
        $rows .= $mkRow($r, $c, 15); $merge[] = "A$r:F$r"; $r++;
    }
    $mc = '<mergeCells count="' . count($merge) . '">' . implode('', array_map(fn($m) => '<mergeCell ref="' . $m . '"/>', $merge)) . '</mergeCells>';
    return $kopf . '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:F' . ($r - 1) . '"/><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr baseColWidth="10" defaultRowHeight="14.25"/><cols><col min="1" max="6" width="15.85546875" style="29" customWidth="1"/><col min="7" max="16384" width="11.42578125" style="29"/></cols><sheetData>' . $rows . '</sheetData>' . $mc
        . '<printOptions horizontalCentered="1"/><pageMargins left="0.3149" right="0.3149" top="0.3543" bottom="0.3543" header="0.3149" footer="0.3149"/><pageSetup paperSize="9" orientation="portrait" fitToWidth="1" fitToHeight="1"/></worksheet>';
}


/** Tussa Linie 6A (Santiago Hórreo <-> Flughafen), Daten aus tussa-6a.json (Quelle: Tussa-PDF, gültig ab 28.05.2026). */
function busArt(string $abfahrt): string {
    [$h] = array_map('intval', explode(':', $abfahrt));
    return $h >= 23 || $h < 6 ? 'Bus nocturno' : ($h >= 21 ? 'Bus tardío' : 'Bus diurno');
}
function blattTussa(array $t, string $kopf, int $nr): string {
    $rows = ''; $merge = []; $r = 0;
    $mk = function (int $nr, string $cells, ?float $ht = null) { return '<row r="' . $nr . '"' . ($ht ? ' ht="' . $ht . '" customHeight="1"' : '') . '>' . $cells . '</row>'; };
    $blocks = [
        ['SANTIAGO - AEROPUERTO (TUSSA 6A) 1,00€', 'hs', ['Hórreo (Est. Intermodal) Salida', 'San Lázaro (solo subida)', 'San Marcos (solo subida)', 'Aeropuerto Llegada aprox.', 'Servicio', 'Tipo de bus']],
        ['AEROPUERTO - SANTIAGO (TUSSA 6A) 1,00€', 'sh', ['Aeropuerto Salida', 'San Marcos (solo bajada)', 'San Lázaro (solo bajada)', 'Hórreo (Est. Intermodal) Llegada aprox.', 'Servicio', 'Tipo de bus']],
    ];
    foreach ([$blocks[$nr]] as [$titel, $key, $head]) {
        $r++; $c = cs("A$r", 61, $titel); foreach (['B', 'C', 'D', 'E', 'F'] as $L) $c .= '<c r="' . $L . $r . '" s="61"/>'; $rows .= $mk($r, $c, 27); $merge[] = "A$r:F$r";
        $r++; $c = ''; foreach (['A', 'B', 'C', 'D', 'E', 'F'] as $i => $L) $c .= cs("$L$r", [16, 17, 51, 52, 53, 54][$i], $head[$i]); $rows .= $mk($r, $c, 42);
        $list = $t[$key]; $n = count($list);
        foreach ($list as $k => $z) {
            $r++;
            $pos = $k === 0 ? 'first' : ($k === $n - 1 ? 'last' : ($k % 2 ? 'a' : 'b'));
            $stl = ['first' => [21, 22], 'a' => [11, 13], 'b' => [25, 26], 'last' => [27, 28]][$pos];
            $d = $z[0] === 'D';
            $c = cn("A$r", $stl[0], frac($z[1]))
               . ($d ? cn("B$r", $stl[1], null) . cn("C$r", $stl[0], null) : cn("B$r", $stl[1], frac($z[3])) . cn("C$r", $stl[0], frac($z[4])))
               . cn("D$r", $stl[1], frac($z[2]))
               . cs("E$r", $stl[0], $d ? 'Directo' : 'con paradas') . cs("F$r", $stl[1], busArt($z[1]));
            $rows .= $mk($r, $c, 13.5);
        }
        $r++; $rows .= $mk($r, '<c r="A' . $r . '" s="62"/>', 6.75);
    }
    $r++;
    foreach (['*Todos los días · Horas de llegada aproximadas*', '*Bus diurno hasta las 20:59 · bus tardío de 21:00 a 22:59*', '*Bus nocturno desde las 23:00 (según hora de salida)*', $t['stand'] ?? '', 'Fuente: Tussa – Transporte urbano de Santiago de Compostela, línea 6A'] as $x) {
        if ($x === '') continue;
        $c = cs("A$r", 60, $x); foreach (['B', 'C', 'D', 'E', 'F'] as $L) $c .= '<c r="' . $L . $r . '" s="60"/>';
        $rows .= $mk($r, $c, 15); $merge[] = "A$r:F$r"; $r++;
    }
    $mc = '<mergeCells count="' . count($merge) . '">' . implode('', array_map(fn($m) => '<mergeCell ref="' . $m . '"/>', $merge)) . '</mergeCells>';
    return $kopf . '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:F' . ($r - 1) . '"/><sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr baseColWidth="10" defaultRowHeight="14.25"/><cols><col min="1" max="6" width="15.85546875" style="29" customWidth="1"/><col min="7" max="16384" width="11.42578125" style="29"/></cols><sheetData>' . $rows . '</sheetData>' . $mc
        . '<printOptions horizontalCentered="1"/><pageMargins left="0.3149" right="0.3149" top="0.3543" bottom="0.3543" header="0.3149" footer="0.3149"/><pageSetup paperSize="9" orientation="portrait" fitToWidth="1" fitToHeight="1"/></worksheet>';
}

$kopf = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">';

$zin = new ZipArchive();
if ($zin->open($vorlage) !== true) fail('Vorlage lässt sich nicht öffnen.');
@unlink($ziel);
$zo = new ZipArchive();
if ($zo->open($ziel, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) fail('Zieldatei kann nicht geschrieben werden: ' . $ziel);
$sheetNo = 0;
for ($i = 0; $i < $zin->numFiles; $i++) {
    $n = $zin->getNameIndex($i);
    if (preg_match('~^xl/worksheets/(sheet\d+)\.xml$~', $n) || preg_match('~^xl/worksheets/_rels/~', $n) || $n === 'xl/workbook.xml' || $n === 'xl/_rels/workbook.xml.rels' || $n === '[Content_Types].xml' || $n === 'docProps/app.xml' || strpos($n, 'xl/printerSettings/') === 0) continue;
    $zo->addFromString($n, (string)$zin->getFromIndex($i));
}
$rid = 0; $sheets = ''; $rels = ''; $ct = '';
foreach ($blaetter as $name => $bl) {
    $rid++;
    $zo->addFromString("xl/worksheets/sheet$rid.xml", blattXml($jf, $bl, $namen, $preise, $standText, $kopf));
    $sheets .= '<sheet name="' . esc($name) . '" sheetId="' . $rid . '" r:id="rId' . $rid . '"/>';
    $rels .= '<Relationship Id="rId' . $rid . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $rid . '.xml"/>';
    $ct .= '<Override PartName="/xl/worksheets/sheet' . $rid . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
}
$tj = json_decode((string)@file_get_contents($dir . DIRECTORY_SEPARATOR . 'tussa-6a.json'), true);
if ($tj) {
    $tj['stand'] = 'Vigente desde el 28.05.2026';
    foreach ([0 => 'Santiago-Aeropuerto', 1 => 'Aeropuerto-Santiago'] as $nr => $sname) {
        $rid++;
        $zo->addFromString("xl/worksheets/sheet$rid.xml", blattTussa($tj, $kopf, $nr));
        $sheets .= '<sheet name="' . $sname . '" sheetId="' . $rid . '" r:id="rId' . $rid . '"/>';
        $rels .= '<Relationship Id="rId' . $rid . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $rid . '.xml"/>';
        $ct .= '<Override PartName="/xl/worksheets/sheet' . $rid . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
    }
}
$wb = (string)$zin->getFromName('xl/workbook.xml');
$wb = preg_replace('~<sheets>.*?</sheets>~s', '<sheets>' . $sheets . '</sheets>', $wb);
$wb = preg_replace('~<mc:AlternateContent.*?</mc:AlternateContent>~s', '', $wb);
$wb = preg_replace('~activeTab="\d+"~', 'activeTab="0"', $wb);
$zo->addFromString('xl/workbook.xml', $wb);
$r0 = (string)$zin->getFromName('xl/_rels/workbook.xml.rels');
$r0 = preg_replace('~<Relationship [^>]*worksheets/sheet\d+\.xml"/>~', '', $r0);
$r0 = str_replace('Id="rId5"', 'Id="rId905"', str_replace('Id="rId6"', 'Id="rId906"', str_replace('Id="rId7"', 'Id="rId907"', $r0)));
$zo->addFromString('xl/_rels/workbook.xml.rels', str_replace('</Relationships>', $rels . '</Relationships>', $r0));
$c0 = (string)$zin->getFromName('[Content_Types].xml');
$c0 = preg_replace('~<Override PartName="/xl/worksheets/sheet\d+\.xml"[^>]*/>~', '', $c0);
$c0 = preg_replace('~<Default Extension="bin"[^>]*/>~', '', $c0);
$c0 = preg_replace('~<Override PartName="/docProps/app\.xml"[^>]*/>~', '', $c0);
$zo->addFromString('[Content_Types].xml', str_replace('</Types>', $ct . '</Types>', $c0));
$zo->close(); $zin->close();
echo "Fertig: $ziel\n$standText\n";
