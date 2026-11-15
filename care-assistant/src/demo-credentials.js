import { constants, openSync, closeSync, readFileSync, writeFileSync, fstatSync } from 'node:fs';
import { randomBytes, randomInt } from 'node:crypto';

// Keep the phone's existing pairing valid across ordinary Mac service restarts.
// This file is private to the current Mac account and excluded from source control.
export function loadDemoCredentials(destination) {
  let fd;
  try {
    try {
      fd = openSync(destination, constants.O_CREAT | constants.O_EXCL | constants.O_RDWR | constants.O_NOFOLLOW, 0o600);
      writeFileSync(fd, JSON.stringify({ apiToken: randomBytes(32).toString('hex'), pairingCode: String(randomInt(100000, 1000000)) }));
      closeSync(fd); fd = undefined;
      fd = openSync(destination, constants.O_RDONLY | constants.O_NOFOLLOW);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      fd = openSync(destination, constants.O_RDONLY | constants.O_NOFOLLOW);
    }
    const info = fstatSync(fd);
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o077)) throw Error('Pairing file must be owned by this Mac account and readable only by its owner.');
    const value = JSON.parse(readFileSync(fd, 'utf8'));
    if (!/^[a-f0-9]{64}$/.test(value.apiToken || '') || !/^[0-9]{6}$/.test(value.pairingCode || '')) throw Error('Invalid saved pairing.');
    return value;
  } finally { if (fd !== undefined) closeSync(fd); }
}
