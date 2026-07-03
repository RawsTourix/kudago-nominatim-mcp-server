param (
    [string]$BaseUrl = "http://127.0.0.1:8011/api/v1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [hashtable]$Body
    )

    $json = $Body | ConvertTo-Json -Depth 20 -Compress
    $utf8Body = [System.Text.Encoding]::UTF8.GetBytes($json)

    return Invoke-RestMethod `
        -Method Post `
        -Uri $Url `
        -ContentType "application/json; charset=utf-8" `
        -Body $utf8Body
}

function Wait-Job {
    param (
        [Parameter(Mandatory = $true)]
        [string]$JobId,

        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        $response = Invoke-RestMethod -Method Get -Uri "$BaseUrl/jobs/$JobId"
        $status = $response.job.status

        if ($status -eq "succeeded" -or $status -eq "failed") {
            return $response
        }

        Start-Sleep -Milliseconds 500
    }

    throw "Job timeout: $JobId"
}

function Test-Job {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [hashtable]$Body,

        [string]$ExpectedResultStatus = "ok"
    )

    Write-Host ""
    Write-Host "=== $Name ==="

    $created = Invoke-JsonPost -Url $Url -Body $Body
    Write-Host "job_id:" $created.job_id

    $job = Wait-Job -JobId $created.job_id
    Write-Host "job.status:" $job.job.status
    Write-Host "result.status:" $job.job.result_payload.status

    if ($job.job.status -ne "succeeded") {
        throw "$Name failed: job.status=$($job.job.status)"
    }

    if ($job.job.result_payload.status -ne $ExpectedResultStatus) {
        throw (
            "$Name failed: expected result.status=$ExpectedResultStatus, " +
            "got $($job.job.result_payload.status)"
        )
    }

    return $created.job_id
}

Write-Host "Smoke test started"
Write-Host "BaseUrl: $BaseUrl"

$nakhabino = -join @(
    0x041D, 0x0430, 0x0445, 0x0430, 0x0431, 0x0438, 0x043D, 0x043E
).ForEach({ [char]$_ })
$moscow = -join @(
    0x041C, 0x043E, 0x0441, 0x043A, 0x0432, 0x0430
).ForEach({ [char]$_ })

Write-Host ""
Write-Host "=== health ==="
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" | Out-Null
Invoke-RestMethod -Method Get -Uri "$BaseUrl/health/db" | Out-Null
Write-Host "health: ok"

Write-Host ""
Write-Host "=== references ==="
Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/references/locations?lang=ru" | Out-Null
Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/references/event-categories?lang=ru" | Out-Null
Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/references/place-categories?lang=ru" | Out-Null
Write-Host "references: ok"

$eventsJob = Test-Job `
    -Name "events.search location=msk" `
    -Url "$BaseUrl/events/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$placesJob = Test-Job `
    -Name "places.search location=msk" `
    -Url "$BaseUrl/places/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$geoJob = Test-Job `
    -Name "geo.resolve Nakhabino" `
    -Url "$BaseUrl/geo/resolve" `
    -Body @{
        query = $nakhabino
        countrycodes = "ru"
        limit = 5
        accept_language = "ru"
    } `
    -ExpectedResultStatus "ambiguous"

$eventsMoscowJob = Test-Job `
    -Name "events.search place_query=Moscow" `
    -Url "$BaseUrl/events/search" `
    -Body @{ place_query = $moscow; page_size = 3; lang = "ru" }

$eventsAmbiguousJob = Test-Job `
    -Name "events.search place_query=Nakhabino" `
    -Url "$BaseUrl/events/search" `
    -Body @{ place_query = $nakhabino; page_size = 3; lang = "ru" } `
    -ExpectedResultStatus "geo_ambiguous"

$placesCoordinatesJob = Test-Job `
    -Name "places.search coordinates" `
    -Url "$BaseUrl/places/search" `
    -Body @{
        lat = 55.751244
        lon = 37.618423
        radius = 5000
        page_size = 3
        lang = "ru"
    }

$placesAmbiguousJob = Test-Job `
    -Name "places.search place_query=Nakhabino" `
    -Url "$BaseUrl/places/search" `
    -Body @{ place_query = $nakhabino; page_size = 3; lang = "ru" } `
    -ExpectedResultStatus "geo_ambiguous"

$movieShowingsJob = Test-Job `
    -Name "movie_showings.search location=msk" `
    -Url "$BaseUrl/movie-showings/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$moviesJob = Test-Job `
    -Name "movies.search location=msk" `
    -Url "$BaseUrl/movies/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$newsJob = Test-Job `
    -Name "news.search location=msk" `
    -Url "$BaseUrl/news/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$newsMoscowJob = Test-Job `
    -Name "news.search place_query=Moscow" `
    -Url "$BaseUrl/news/search" `
    -Body @{ place_query = $moscow; page_size = 3; lang = "ru" }

$newsAmbiguousJob = Test-Job `
    -Name "news.search place_query=Nakhabino" `
    -Url "$BaseUrl/news/search" `
    -Body @{ place_query = $nakhabino; page_size = 3; lang = "ru" } `
    -ExpectedResultStatus "geo_ambiguous"

$listsJob = Test-Job `
    -Name "lists.search location=msk" `
    -Url "$BaseUrl/lists/search" `
    -Body @{ location = "msk"; page_size = 3; lang = "ru" }

$listsMoscowJob = Test-Job `
    -Name "lists.search place_query=Moscow" `
    -Url "$BaseUrl/lists/search" `
    -Body @{ place_query = $moscow; page_size = 3; lang = "ru" }

$listsAmbiguousJob = Test-Job `
    -Name "lists.search place_query=Nakhabino" `
    -Url "$BaseUrl/lists/search" `
    -Body @{ place_query = $nakhabino; page_size = 3; lang = "ru" } `
    -ExpectedResultStatus "geo_ambiguous"

Write-Host ""
Write-Host "=== objects ==="
Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/objects/location/msk?lang=ru" | Out-Null
Write-Host "objects/location/msk: ok"

Write-Host ""
Write-Host "=== upstream-calls ==="
$upstream = Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/jobs/$listsJob/upstream-calls"

if ($upstream.upstream_calls.Count -lt 1) {
    throw "lists.search did not record an upstream call"
}

Write-Host "lists upstream calls:" $upstream.upstream_calls.Count

Write-Host ""
Write-Host "Smoke test completed successfully"
