const test = require("node:test");
const assert = require("node:assert/strict");

const { buildServer } = require("../src/server");
const {
  EV_CHARGER_BASE_URL,
  extractEvChargerPayload,
  fetchEvCharger,
  normalizeEvChargerQuery
} = require("../src/ev-charger");

test("EV charger normalizers apply defaults and narrow operation filters", () => {
  assert.deepEqual(normalizeEvChargerQuery("info", {
    zcode: "11",
    zscode: "11680",
    statId: "ME000001",
    chgerId: "01",
    location: "강남구",
    pageNo: "2",
    numOfRows: "100"
  }), {
    operation: "info",
    upstreamOperation: "getChargerInfo",
    pageNo: 2,
    numOfRows: 100,
    zcode: "11",
    zscode: "11680",
    statId: "ME000001",
    chgerId: "01",
    location: "강남구"
  });

  assert.deepEqual(normalizeEvChargerQuery("status", {
    statId: "ME000001",
    limitYn: "y",
    period: "10"
  }), {
    operation: "status",
    upstreamOperation: "getChargerStatus",
    pageNo: 1,
    numOfRows: 10,
    statId: "ME000001",
    limitYn: "Y",
    period: 10
  });
});

test("EV charger normalizers reject caller-controlled auth/format and malformed filters", () => {
  assert.throws(() => normalizeEvChargerQuery("info", { serviceKey: "caller-key" }), /serviceKey/);
  assert.throws(() => normalizeEvChargerQuery("info", { dataType: "XML" }), /dataType/);
  assert.throws(() => normalizeEvChargerQuery("info", { pageNo: "1.5" }), /pageNo/);
  assert.throws(() => normalizeEvChargerQuery("info", { numOfRows: "101" }), /numOfRows/);
  assert.throws(() => normalizeEvChargerQuery("info", { zcode: "123" }), /zcode/);
  assert.throws(() => normalizeEvChargerQuery("info", { zscode: "abc" }), /zscode/);
  assert.throws(() => normalizeEvChargerQuery("status", { limitYn: "maybe" }), /limitYn/);
  assert.throws(() => normalizeEvChargerQuery("status", { period: "0" }), /period/);
  assert.throws(() => normalizeEvChargerQuery("status", { location: "서울" }), /location/);
  assert.throws(() => normalizeEvChargerQuery("info", { statId: "x".repeat(41) }), /statId/);
});

test("EV charger payload extraction accepts direct and response envelopes", () => {
  assert.deepEqual(extractEvChargerPayload({
    pageNo: 1,
    numOfRows: 10,
    totalCount: 1,
    items: { item: { statId: "ME000001" } }
  }).items, [{ statId: "ME000001" }]);

  assert.deepEqual(extractEvChargerPayload({
    response: {
      header: { resultCode: "00", resultMsg: "NORMAL SERVICE." },
      body: { pageNo: 1, numOfRows: 10, totalCount: 0, items: "" }
    }
  }).items, []);
});

test("EV charger fetch injects the server key, forces JSON, and never leaks the key", async () => {
  let seenUrl = "";
  const result = await fetchEvCharger({
    params: normalizeEvChargerQuery("info", { location: "서울", numOfRows: 5 }),
    serviceKey: "server secret +/==",
    fetchImpl: async (url) => {
      seenUrl = String(url);
      return new Response(JSON.stringify({
        pageNo: 1,
        numOfRows: 5,
        totalCount: 1,
        items: { item: [{ statId: "ME000001", statNm: "시청 충전소" }] }
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
  });

  const parsedUrl = new URL(seenUrl);
  assert.equal(`${parsedUrl.origin}${parsedUrl.pathname}`, `${EV_CHARGER_BASE_URL}/getChargerInfo`);
  assert.equal(parsedUrl.searchParams.get("serviceKey"), "server secret +/==");
  assert.equal(parsedUrl.searchParams.get("dataType"), "JSON");
  assert.equal(parsedUrl.searchParams.get("location"), "서울");
  assert.equal(result.error, undefined);
  assert.equal(result.total_count, 1);
  assert.equal(JSON.stringify(result).includes("server secret"), false);
});

test("EV charger fetch classifies semantic, XML, empty, and invalid JSON failures", async () => {
  const params = normalizeEvChargerQuery("status", { statId: "ME000001" });
  const cases = [
    new Response(JSON.stringify({ response: { header: { resultCode: "30", resultMsg: "SERVICE KEY IS NOT REGISTERED" } } }), { status: 200 }),
    new Response("<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>", { status: 200, headers: { "content-type": "application/xml" } }),
    new Response("", { status: 200 }),
    new Response("not-json", { status: 200, headers: { "content-type": "application/json" } }),
    new Response("{}", { status: 200, headers: { "content-type": "application/json" } })
  ];

  for (const response of cases) {
    const result = await fetchEvCharger({ params, serviceKey: "secret", fetchImpl: async () => response });
    assert.equal(result.status_code, 502);
    assert.match(result.error, /^upstream_/);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("EV charger routes validate before fetch, report missing key, and cache successes only", async (t) => {
  const originalFetch = global.fetch;
  const calls = [];
  global.fetch = async (url) => {
    calls.push(String(url));
    return new Response(JSON.stringify({
      pageNo: 1,
      numOfRows: 10,
      totalCount: 1,
      items: { item: [{ statId: "ME000001", chgerId: "01", stat: "2" }] }
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const app = buildServer({ env: { DATA_GO_KR_API_KEY: "proxy-key" } });
  t.after(async () => {
    global.fetch = originalFetch;
    await app.close();
  });

  const malformed = await app.inject({ method: "GET", url: "/v1/ev-charger/status?limitYn=maybe" });
  assert.equal(malformed.statusCode, 400);
  assert.equal(calls.length, 0);

  const first = await app.inject({ method: "GET", url: "/v1/ev-charger/status?statId=ME000001" });
  assert.equal(first.statusCode, 200);
  assert.equal(first.json().proxy.cache.hit, false);
  const cached = await app.inject({ method: "GET", url: "/v1/ev-charger/status?statId=ME000001" });
  assert.equal(cached.statusCode, 200);
  assert.equal(cached.json().proxy.cache.hit, true);
  assert.equal(calls.length, 1);

  const missing = buildServer({ env: {} });
  t.after(() => missing.close());
  const unavailable = await missing.inject({ method: "GET", url: "/v1/ev-charger/info?location=서울" });
  assert.equal(unavailable.statusCode, 503);
  assert.equal(unavailable.json().error, "upstream_not_configured");
});

test("EV charger semantic errors return 502 and are not cached", async (t) => {
  const originalFetch = global.fetch;
  let callCount = 0;
  global.fetch = async () => {
    callCount += 1;
    return new Response(JSON.stringify({
      response: { header: { resultCode: "30", resultMsg: "SERVICE KEY IS NOT REGISTERED" } }
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const app = buildServer({ env: { DATA_GO_KR_API_KEY: "must-not-leak" } });
  t.after(async () => {
    global.fetch = originalFetch;
    await app.close();
  });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await app.inject({ method: "GET", url: "/v1/ev-charger/info?zcode=11" });
    assert.equal(response.statusCode, 502);
    assert.equal(response.json().error, "upstream_forbidden");
    assert.equal(response.body.includes("must-not-leak"), false);
  }
  assert.equal(callCount, 2);
});
