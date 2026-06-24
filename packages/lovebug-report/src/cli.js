#!/usr/bin/env node
const {
  findRegion,
  getAreas,
  getClusters,
  listRegions,
  reportLovebug,
  searchLovebugRegions
} = require("./index")

async function main(options = parseArgs(process.argv.slice(2)), io = console) {
  if (options.help) {
    printHelp(io)
    return
  }

  const command = options.command || "search"
  let result
  if (command === "search") result = await searchLovebugRegions(options)
  else if (command === "list") result = await listRegions(options)
  else if (command === "find") result = await findRegion(options.query, options)
  else if (command === "areas") result = await getAreas(options)
  else if (command === "clusters") result = await getClusters(options)
  else if (command === "report") result = await reportLovebug(options)
  else throw new Error(`unknown command: ${command}`)

  io.log(JSON.stringify(result, null, 2))
}

function parseArgs(argv) {
  const options = {}
  if (argv[0] && !argv[0].startsWith("-")) options.command = argv.shift()
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === "--query" || arg === "-q" || arg === "--region") options.query = argv[++i] || ""
    else if (arg === "--gu-code" || arg === "--gu") options.guCode = argv[++i] || ""
    else if (arg === "--level") options.level = argv[++i] || ""
    else if (arg === "--context") options.context = argv[++i] || ""
    else if (arg === "--lng" || arg === "--longitude") options.lng = argv[++i] || ""
    else if (arg === "--lat" || arg === "--latitude") options.lat = argv[++i] || ""
    else if (arg === "--accuracy" || arg === "--accuracy-m") options.accuracyM = argv[++i] || ""
    else if (arg === "--device-hash") options.deviceHash = argv[++i] || ""
    else if (arg === "--image-url") options.imageUrl = argv[++i] || ""
    else if (arg === "--indoor") options.indoor = true
    else if (arg === "--outdoor") options.indoor = false
    else if (arg === "--limit") options.limit = argv[++i] || ""
    else if (arg === "--level-type") options.level = argv[++i] || ""
    else if (arg === "--date") options.date = argv[++i] || ""
    else if (arg === "--historical-year" || arg === "--year") options.historicalYear = argv[++i] || ""
    else if (arg === "--historical-week" || arg === "--week") options.historicalWeek = argv[++i] || ""
    else if (arg === "--include-areas") options.includeAreas = true
    else if (arg === "--no-areas") options.includeAreas = false
    else if (arg === "--include-polygon") options.includePolygon = true
    else if (arg === "--help" || arg === "-h") options.help = true
    else if (!options.query) options.query = arg
  }
  return options
}

function printHelp(io = console) {
  io.log(`Usage: lovebug-report <command> [options]

Query lovebug.com public map surfaces and submit anonymous lovebug reports through the same public Supabase RPC used by the site.

Commands:
  lovebug-report search --query 중랑 [--include-areas]   Search gu/area lovebug status.
  lovebug-report list --limit 10                         List top gu score rows.
  lovebug-report find --query 동안                       Return the best matching gu row.
  lovebug-report areas --query 중랑                      Fetch eup/myeon/dong area snapshots.
  lovebug-report clusters                                Fetch sigungu cluster snapshots.
  lovebug-report report --gu-code 11070 --level 많아요 --context 길거리 --lng 127.09 --lat 37.59 --accuracy 25 --device-hash <stable-id>

Report options:
  --gu-code <code>        Required sigungu code from search/list output.
  --level <0-3|label>     잠잠해요, 살짝 보임, 많아요, 매우 많아요.
  --context <label>       실내, 길거리, 공원, 지하철·버스, 상가, 기타.
  --lng, --lat <number>   Current coordinates. lovebug.com rejects coordinates outside the gu.
  --accuracy <meters>     GPS accuracy in meters.
  --device-hash <id>      Required stable anonymous device id for duplicate/rate limits.
  --image-url <url>       Optional already-uploaded image URL.

Lookup options:
  --query, -q <text>      Region name/code query.
  --limit <number>        Max rows.
  --date <YYYY-MM-DD>     Snapshot date when supported by upstream.
  --year <YYYY>           Historical year (default 2026).
  --week <number>         Historical week.
  --no-areas              Skip area snapshot lookup in search.
`)
}

function formatError(error) {
  if (process.env.LOVEBUG_REPORT_DEBUG && error && error.stack) return error.stack
  if (error && error.code && error.message) return `Error [${error.code}]: ${error.message}`
  if (error && error.message) return `Error: ${error.message}`
  return String(error)
}

function run(argv = process.argv.slice(2), io = console) {
  return main(parseArgs(argv), io).catch((error) => {
    io.error(formatError(error))
    process.exitCode = 1
  })
}

if (require.main === module) run()

module.exports = { formatError, main, parseArgs, printHelp, run }
