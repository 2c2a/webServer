'use strict';

const forge = require('node-forge');
const crypto = require('crypto');

/**
 * Generate a new Certificate Authority (CA)
 * @param {object} options - CA options
 * @param {string} options.name - CA common name (default: '2c2a CA')
 * @param {number} options.keySize - Key size in bits (default: 4096)
 * @param {number} options.yearsValid - Years until expiration (default: 10)
 * @returns {object} { caKeyPem, caCertPem, thumbprint }
 */
function generateCA(options = {}) {
  const name = options.name || '2c2a CA';
  const keySize = options.keySize || 4096;
  const yearsValid = options.yearsValid || 10;

  console.log(`[Certificate] Generating CA: ${name} (${keySize}-bit key)`);

  // Generate key pair
  const keys = forge.pki.rsa.generateKeyPair(keySize);

  // Create certificate
  const cert = forge.pki.createCertificate();
  cert.publicKey = keys.publicKey;
  cert.serialNumber = crypto.randomBytes(16).toString('hex');

  // Set validity
  const now = new Date();
  cert.validity.notBefore = now;
  cert.validity.notAfter = new Date(now.getFullYear() + yearsValid, now.getMonth(), now.getDate());

  // Set subject and issuer (self-signed)
  const attrs = [
    { name: 'commonName', value: name },
    { name: 'organizationName', value: '2c2a' },
    { name: 'countryName', value: 'CN' },
  ];
  cert.setSubject(attrs);
  cert.setIssuer(attrs);

  // Set extensions for CA
  cert.setExtensions([
    { name: 'basicConstraints', cA: true },
    { name: 'keyUsage', keyCertSign: true, cRLSign: true },
    {
      name: 'subjectKeyIdentifier',
    },
    {
      name: 'authorityKeyIdentifier',
      authorityCertIssuer: true,
      serialNumber: cert.serialNumber,
    },
  ]);

  // Self-sign
  cert.sign(keys.privateKey, forge.md.sha256.create());

  // Convert to PEM
  const caKeyPem = forge.pki.privateKeyToPem(keys.privateKey);
  const caCertPem = forge.pki.certificateToPem(cert);

  // Calculate thumbprint (SHA-1 of DER)
  const derBytes = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();
  const thumbprint = forge.md.sha1.create().update(derBytes).digest().toHex().toUpperCase();

  console.log(`[Certificate] CA generated. Thumbprint: ${thumbprint}`);

  return {
    caKeyPem,
    caCertPem,
    thumbprint,
    expiresAt: cert.validity.notAfter.toISOString(),
  };
}

/**
 * Issue a server certificate signed by the CA
 * @param {string} caKeyPem - CA private key PEM
 * @param {string} caCertPem - CA certificate PEM
 * @param {string} hostname - Server hostname
 * @param {string} ipAddress - Server IP address
 * @param {object} options - Certificate options
 * @param {number} options.keySize - Key size in bits (default: 2048)
 * @param {number} options.yearsValid - Years until expiration (default: 1)
 * @returns {object} { certPem, keyPem, thumbprint }
 */
function issueServerCert(caKeyPem, caCertPem, hostname, ipAddress, options = {}) {
  const keySize = options.keySize || 2048;
  const yearsValid = options.yearsValid || 1;

  console.log(`[Certificate] Issuing server cert for ${hostname} (${ipAddress || 'no IP'})`);

  // Parse CA key and cert
  const caKey = forge.pki.privateKeyFromPem(caKeyPem);
  const caCert = forge.pki.certificateFromPem(caCertPem);

  // Generate key pair for server
  const keys = forge.pki.rsa.generateKeyPair(keySize);

  // Create certificate
  const cert = forge.pki.createCertificate();
  cert.publicKey = keys.publicKey;
  cert.serialNumber = crypto.randomBytes(16).toString('hex');

  // Set validity
  const now = new Date();
  cert.validity.notBefore = now;
  cert.validity.notAfter = new Date(now.getFullYear() + yearsValid, now.getMonth(), now.getDate());

  // Set subject
  cert.setSubject([
    { name: 'commonName', value: hostname },
    { name: 'organizationName', value: '2c2a' },
  ]);

  // Set issuer from CA
  cert.setIssuer(caCert.subject.attributes);

  // Build SAN list
  const altNames = [
    { type: 2, value: hostname }, // DNS name
  ];

  if (ipAddress) {
    altNames.push({ type: 7, ip: ipAddress }); // IP address
  }

  // Set extensions
  cert.setExtensions([
    { name: 'basicConstraints', cA: false },
    {
      name: 'keyUsage',
      digitalSignature: true,
      keyEncipherment: true,
    },
    {
      name: 'extKeyUsage',
      serverAuth: true,
    },
    {
      name: 'subjectAltName',
      altNames: altNames,
    },
    {
      name: 'subjectKeyIdentifier',
    },
    {
      name: 'authorityKeyIdentifier',
      authorityCertIssuer: true,
      serialNumber: caCert.serialNumber,
    },
  ]);

  // Sign with CA key
  cert.sign(caKey, forge.md.sha256.create());

  // Convert to PEM
  const certPem = forge.pki.certificateToPem(cert);
  const keyPem = forge.pki.privateKeyToPem(keys.privateKey);

  // Calculate thumbprint
  const derBytes = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();
  const thumbprint = forge.md.sha1.create().update(derBytes).digest().toHex().toUpperCase();

  console.log(`[Certificate] Server cert issued. Thumbprint: ${thumbprint}`);

  return {
    certPem,
    keyPem,
    thumbprint,
    expiresAt: cert.validity.notAfter.toISOString(),
  };
}

/**
 * Issue a client certificate signed by the CA
 * @param {string} caKeyPem - CA private key PEM
 * @param {string} caCertPem - CA certificate PEM
 * @param {string} upnValue - UPN (User Principal Name) value
 * @param {object} options - Certificate options
 * @param {number} options.keySize - Key size in bits (default: 2048)
 * @param {number} options.yearsValid - Years until expiration (default: 1)
 * @returns {object} { certPem, keyPem, thumbprint }
 */
function issueClientCert(caKeyPem, caCertPem, upnValue, options = {}) {
  const keySize = options.keySize || 2048;
  const yearsValid = options.yearsValid || 1;

  console.log(`[Certificate] Issuing client cert for UPN: ${upnValue}`);

  // Parse CA key and cert
  const caKey = forge.pki.privateKeyFromPem(caKeyPem);
  const caCert = forge.pki.certificateFromPem(caCertPem);

  // Generate key pair for client
  const keys = forge.pki.rsa.generateKeyPair(keySize);

  // Create certificate
  const cert = forge.pki.createCertificate();
  cert.publicKey = keys.publicKey;
  cert.serialNumber = crypto.randomBytes(16).toString('hex');

  // Set validity
  const now = new Date();
  cert.validity.notBefore = now;
  cert.validity.notAfter = new Date(now.getFullYear() + yearsValid, now.getMonth(), now.getDate());

  // Set subject
  cert.setSubject([
    { name: 'commonName', value: upnValue },
    { name: 'organizationName', value: '2c2a' },
  ]);

  // Set issuer from CA
  cert.setIssuer(caCert.subject.attributes);

  // Set extensions
  cert.setExtensions([
    { name: 'basicConstraints', cA: false },
    {
      name: 'keyUsage',
      digitalSignature: true,
      keyEncipherment: true,
    },
    {
      name: 'extKeyUsage',
      clientAuth: true,
    },
    {
      name: 'subjectAltName',
      altNames: [
        { type: 1, value: upnValue }, // RFC822 name (email/UPN)
      ],
    },
    {
      name: 'subjectKeyIdentifier',
    },
    {
      name: 'authorityKeyIdentifier',
      authorityCertIssuer: true,
      serialNumber: caCert.serialNumber,
    },
  ]);

  // Sign with CA key
  cert.sign(caKey, forge.md.sha256.create());

  // Convert to PEM
  const certPem = forge.pki.certificateToPem(cert);
  const keyPem = forge.pki.privateKeyToPem(keys.privateKey);

  // Calculate thumbprint
  const derBytes = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();
  const thumbprint = forge.md.sha1.create().update(derBytes).digest().toHex().toUpperCase();

  console.log(`[Certificate] Client cert issued. Thumbprint: ${thumbprint}`);

  return {
    certPem,
    keyPem,
    thumbprint,
    expiresAt: cert.validity.notAfter.toISOString(),
  };
}

// Task handler mapping
const handlers = {
  generate_ca: (task) => generateCA(task.payload.options || {}),
  issue_server_cert: (task) => issueServerCert(
    task.payload.caKeyPem,
    task.payload.caCertPem,
    task.payload.hostname,
    task.payload.ipAddress,
    task.payload.options || {}
  ),
  issue_client_cert: (task) => issueClientCert(
    task.payload.caKeyPem,
    task.payload.caCertPem,
    task.payload.upnValue,
    task.payload.options || {}
  ),
};

module.exports = {
  generateCA,
  issueServerCert,
  issueClientCert,
  handlers,
};
