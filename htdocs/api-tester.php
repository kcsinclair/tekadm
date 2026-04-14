<?php
/*
 * api-tester.php — Standalone CRUD API endpoint for API testing
 *
 * Drop onto any PHP-enabled web server. Data is stored as a JSON file on disk.
 * All requests require an API token via the Authorization header or ?token= query param.
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
    $auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (preg_match('/^Bearer\s+(.+)$/i', $auth, $m)) {
        return trim($m[1]);
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
            'auth'    => 'Authorization: Bearer <token> header or ?token=<token> query param',
        ]);
        break;
}
