<?php
/*
 * api-tester.php — Standalone CRUD API endpoint for API testing
 *
 * Drop onto any PHP-enabled web server. Data is stored as a JSON file on disk.
 * All requests require an API token. Supported methods (in priority order):
 *   1. Authorization: Bearer <token>  (needs .htaccess on Apache CGI/FastCGI)
 *   2. X-API-Token: <token>           (custom header, never stripped by Apache)
 *   3. ?token=<token>                 (query parameter fallback)
 *
 * Endpoints (all via this single script):
 *   GET    ?action=list                  — list all animals
 *   GET    ?action=read&uuid=<uuid>      — read one animal
 *   POST   ?action=create                — create animal (JSON body)
 *   PUT    ?action=update&uuid=<uuid>    — update animal (JSON body)
 *   DELETE ?action=delete&uuid=<uuid>    — delete animal
 *
 * Copyright (c) 2026 Keith Sinclair — MIT License
 */

// ============================================================================
// Configuration
// ============================================================================

$API_TOKEN   = 'changeme-secret-token-123';
$DATA_FILE   = '/tmp/api-tester-data.json';

// ============================================================================
// Helpers
// ============================================================================

function json_response($data, $status = 200) {
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    exit;
}

function json_error($message, $status = 400) {
    json_response(['error' => $message], $status);
}

function load_data($file) {
    if (!file_exists($file)) {
        return [];
    }
    $json = file_get_contents($file);
    $data = json_decode($json, true);
    return is_array($data) ? $data : [];
}

function save_data($file, $data) {
    $dir = dirname($file);
    if (!is_dir($dir)) {
        mkdir($dir, 0755, true);
    }
    file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n", LOCK_EX);
}

function generate_uuid() {
    // RFC 4122 v4 UUID
    $bytes = random_bytes(16);
    $bytes[6] = chr((ord($bytes[6]) & 0x0f) | 0x40); // version 4
    $bytes[8] = chr((ord($bytes[8]) & 0x3f) | 0x80); // variant 1
    return sprintf(
        '%s-%s-%s-%s-%s',
        bin2hex(substr($bytes, 0, 4)),
        bin2hex(substr($bytes, 4, 2)),
        bin2hex(substr($bytes, 6, 2)),
        bin2hex(substr($bytes, 8, 2)),
        bin2hex(substr($bytes, 10, 6))
    );
}

function validate_animal($input, $require_all = true) {
    $fields = ['name', 'count', 'location', 'date_seen'];
    $animal = [];
    $errors = [];

    foreach ($fields as $field) {
        if (isset($input[$field])) {
            $animal[$field] = $input[$field];
        } elseif ($require_all) {
            $errors[] = "Missing required field: $field";
        }
    }

    // Validate types when present
    if (isset($animal['count']) && !is_numeric($animal['count'])) {
        $errors[] = "'count' must be numeric";
    } elseif (isset($animal['count'])) {
        $animal['count'] = (int) $animal['count'];
    }

    if (isset($animal['date_seen']) && !strtotime($animal['date_seen'])) {
        $errors[] = "'date_seen' must be a valid date string";
    }

    if ($errors) {
        json_error(implode('; ', $errors), 422);
    }

    return $animal;
}

// ============================================================================
// Authentication
// ============================================================================

function get_token() {
    // Check Authorization: Bearer <token>
    // Apache/CGI often strips this header — check multiple server vars
    $auth = '';
    foreach (['HTTP_AUTHORIZATION', 'REDIRECT_HTTP_AUTHORIZATION', 'HTTP_X_AUTHORIZATION'] as $key) {
        if (!empty($_SERVER[$key])) {
            $auth = $_SERVER[$key];
            break;
        }
    }
    // Also try apache_request_headers() which works under mod_php
    if (!$auth && function_exists('apache_request_headers')) {
        $headers = apache_request_headers();
        $auth = $headers['Authorization'] ?? $headers['authorization'] ?? '';
    }
    if (preg_match('/^Bearer\s+(.+)$/i', $auth, $m)) {
        return trim($m[1]);
    }
    // Check custom header: X-API-Token (not stripped by Apache)
    if (!empty($_SERVER['HTTP_X_API_TOKEN'])) {
        return trim($_SERVER['HTTP_X_API_TOKEN']);
    }
    // Fall back to ?token= query parameter
    return $_GET['token'] ?? '';
}

$provided_token = get_token();
if ($provided_token !== $API_TOKEN) {
    json_error('Unauthorized — provide a valid API token via Authorization: Bearer <token> header or ?token= parameter', 401);
}

// ============================================================================
// Routing
// ============================================================================

$action = $_GET['action'] ?? '';
$uuid   = $_GET['uuid']   ?? '';
$method = $_SERVER['REQUEST_METHOD'];

switch ($action) {

    // ---- LIST all animals ---------------------------------------------------
    case 'list':
        if ($method !== 'GET') json_error('Use GET for list', 405);
        $animals = load_data($DATA_FILE);
        json_response([
            'count'   => count($animals),
            'animals' => array_values($animals),
        ]);
        break;

    // ---- READ one animal ----------------------------------------------------
    case 'read':
        if ($method !== 'GET') json_error('Use GET for read', 405);
        if (!$uuid) json_error('uuid parameter required');
        $animals = load_data($DATA_FILE);
        if (!isset($animals[$uuid])) {
            json_error("Animal not found: $uuid", 404);
        }
        json_response($animals[$uuid]);
        break;

    // ---- CREATE a new animal ------------------------------------------------
    case 'create':
        if ($method !== 'POST') json_error('Use POST for create', 405);
        $input = json_decode(file_get_contents('php://input'), true);
        if (!$input) json_error('Request body must be valid JSON');

        $animal = validate_animal($input, true);
        $animal['uuid']       = generate_uuid();
        $animal['created_at'] = date('c');
        $animal['updated_at'] = date('c');

        $animals = load_data($DATA_FILE);
        $animals[$animal['uuid']] = $animal;
        save_data($DATA_FILE, $animals);

        json_response($animal, 201);
        break;

    // ---- UPDATE an existing animal ------------------------------------------
    case 'update':
        if ($method !== 'PUT' && $method !== 'PATCH') json_error('Use PUT or PATCH for update', 405);
        if (!$uuid) json_error('uuid parameter required');

        $animals = load_data($DATA_FILE);
        if (!isset($animals[$uuid])) {
            json_error("Animal not found: $uuid", 404);
        }

        $input = json_decode(file_get_contents('php://input'), true);
        if (!$input) json_error('Request body must be valid JSON');

        $updates = validate_animal($input, false);  // partial update OK
        $animals[$uuid] = array_merge($animals[$uuid], $updates);
        $animals[$uuid]['updated_at'] = date('c');
        save_data($DATA_FILE, $animals);

        json_response($animals[$uuid]);
        break;

    // ---- DELETE an animal ---------------------------------------------------
    case 'delete':
        if ($method !== 'DELETE') json_error('Use DELETE for delete', 405);
        if (!$uuid) json_error('uuid parameter required');

        $animals = load_data($DATA_FILE);
        if (!isset($animals[$uuid])) {
            json_error("Animal not found: $uuid", 404);
        }

        $deleted = $animals[$uuid];
        unset($animals[$uuid]);
        save_data($DATA_FILE, $animals);

        json_response(['deleted' => $deleted]);
        break;

    // ---- Unknown or missing action ------------------------------------------
    default:
        // Serve HTML view for browsers, JSON for API clients
        $accept = $_SERVER['HTTP_ACCEPT'] ?? '';
        if (strpos($accept, 'text/html') !== false) {
            html_view($DATA_FILE);
        }
        json_response([
            'name'    => 'api-tester',
            'version' => '1.0',
            'actions' => [
                'GET    ?action=list'              => 'List all animals',
                'GET    ?action=read&uuid=<uuid>'  => 'Read one animal',
                'POST   ?action=create'            => 'Create animal (JSON body: name, count, location, date_seen)',
                'PUT    ?action=update&uuid=<uuid>' => 'Update animal (JSON body: partial fields OK)',
                'DELETE ?action=delete&uuid=<uuid>' => 'Delete animal',
            ],
            'auth'    => 'Authorization: Bearer <token> | X-API-Token: <token> | ?token=<token>',
        ]);
        break;
}


// ============================================================================
// HTML Browser View
// ============================================================================

function html_view($data_file) {
    $animals = load_data($data_file);
    $count = count($animals);
    // Sort by name for display
    usort($animals, function($a, $b) { return strcasecmp($a['name'] ?? '', $b['name'] ?? ''); });

    header('Content-Type: text/html; charset=utf-8');
    echo <<<'HTML_HEAD'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API Tester — Animal Sightings</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         background: #f5f7fa; color: #333; padding: 2rem; }
  h1 { margin-bottom: .25rem; }
  .subtitle { color: #666; margin-bottom: 1.5rem; }
  table { width: 100%; border-collapse: collapse; background: #fff;
          box-shadow: 0 1px 3px rgba(0,0,0,.1); border-radius: 6px; overflow: hidden; }
  th, td { padding: .65rem .9rem; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #2c3e50; color: #fff; font-weight: 600; font-size: .85rem;
       text-transform: uppercase; letter-spacing: .03em; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f0f4f8; }
  td.count { text-align: right; font-variant-numeric: tabular-nums; }
  .uuid { font-family: "SF Mono", Monaco, Consolas, monospace; font-size: .8rem; color: #888; }
  .empty { text-align: center; padding: 3rem; color: #999; }
  .meta { margin-top: 1rem; font-size: .85rem; color: #888; }
</style>
</head>
<body>
<h1>Animal Sightings</h1>
HTML_HEAD;

    echo "<p class=\"subtitle\">$count record" . ($count !== 1 ? 's' : '') . "</p>\n";

    if ($count === 0) {
        echo '<div class="empty">No animals recorded yet. Use the API to add some.</div>';
    } else {
        echo "<table>\n<thead><tr>";
        echo "<th>Name</th><th>Count</th><th>Location</th><th>Date Seen</th><th>UUID</th>";
        echo "</tr></thead>\n<tbody>\n";
        foreach ($animals as $a) {
            $name     = htmlspecialchars($a['name'] ?? '');
            $cnt      = htmlspecialchars($a['count'] ?? '');
            $location = htmlspecialchars($a['location'] ?? '');
            $date     = htmlspecialchars($a['date_seen'] ?? '');
            $uuid     = htmlspecialchars($a['uuid'] ?? '');
            echo "<tr><td>$name</td><td class=\"count\">$cnt</td>"
               . "<td>$location</td><td>$date</td><td class=\"uuid\">$uuid</td></tr>\n";
        }
        echo "</tbody>\n</table>\n";
    }

    echo '<p class="meta">api-tester v1.0 &mdash; data file: '
       . htmlspecialchars($data_file) . '</p>';
    echo "\n</body>\n</html>\n";
    exit;
}
