#!/usr/bin/env node

// Exponential backoff prevents thundering herd on gateway restart
const timeoutMs = 5000; // timeout ms

// eslint-disable-next-line no-console
console.log("booting", timeoutMs);

// prettier-ignore
const matrix = [1, 2, 3];

// biome-ignore lint/suspicious/noExplicitAny: legacy bridge
const anyBridge = matrix;

// istanbul ignore next
export function exportedHelper(x) {
  return x + 1;
}

/**
 * Retries failed requests using jittered exponential backoff.
 */
function sharedClamp(value) {
  return Math.max(0, value);
}

function buildPayload(raw) {
  const step1 = sharedClamp(raw);
  const step2 = sharedClamp(step1 + 1);
  return { payload: step2 };
}

class Worker {
  constructor(name) {
    this.name = name;
  }

  main() {
    return buildPayload(1);
  }

  testRunner() {
    return anyBridge;
  }

  async safeFetch(client) {
    try {
      return await client.get();
    } catch (err) {
      console.error("request failed", err);
      return null;
    }
  }
}
