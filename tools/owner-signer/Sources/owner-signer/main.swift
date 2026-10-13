// owner-signer: sign Nexus Owner grants with a user-presence–gated Secure Enclave key (#1750 phase 2).
//
// The private key is created inside the Secure Enclave and never leaves it; the
// file on disk is an opaque handle that only this Mac's Secure Enclave can use.
// Every signature requires fresh user presence (Touch ID, Apple Watch, or the
// Mac login password in the system prompt), so a process running under the
// Owner's account cannot sign without the Owner.
//
//   owner-signer init            create the key (once) and print the public key
//   owner-signer pubkey          print the public key PEM
//   owner-signer sign FILE       user-presence prompt, then print the base64 DER signature
//
// FILE must be the canonical payload written by
// `scripts/ops/owner_attestation.py draft`; the prompt summary is parsed from the
// exact bytes being signed.

import CryptoKit
import Foundation
import LocalAuthentication
import Security

let keyDirectory = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Nexus/owner-signer", isDirectory: true)
let keyFile = keyDirectory.appendingPathComponent("secure-enclave-key.bin")

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

func loadKey(context: LAContext? = nil) -> SecureEnclave.P256.Signing.PrivateKey {
    guard let handle = try? Data(contentsOf: keyFile) else {
        fail("no key found; run `owner-signer init` first")
    }
    do {
        return try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: handle, authenticationContext: context)
    } catch {
        fail("cannot load Secure Enclave key: \(error)")
    }
}

func printPublicKey(_ key: SecureEnclave.P256.Signing.PrivateKey) {
    let der = key.publicKey.derRepresentation
    let keyID = SHA256.hash(data: der).map { String(format: "%02x", $0) }.joined()
    print(key.publicKey.pemRepresentation)
    FileHandle.standardError.write(Data("key_id: \(keyID)\n".utf8))
}

func initKey() {
    guard SecureEnclave.isAvailable else { fail("this Mac has no Secure Enclave") }
    if FileManager.default.fileExists(atPath: keyFile.path) {
        fail("a key already exists at \(keyFile.path); refusing to replace it")
    }
    var error: Unmanaged<CFError>?
    guard let access = SecAccessControlCreateWithFlags(
        nil,
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        [.privateKeyUsage, .userPresence],
        &error
    ) else {
        fail("cannot create access control: \(String(describing: error))")
    }
    do {
        let key = try SecureEnclave.P256.Signing.PrivateKey(accessControl: access)
        try FileManager.default.createDirectory(
            at: keyDirectory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        try key.dataRepresentation.write(to: keyFile, options: [.withoutOverwriting])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: keyFile.path)
        printPublicKey(key)
    } catch {
        fail("cannot create Secure Enclave key: \(error)")
    }
}

func summary(of payload: Data) -> String {
    // Parse strictly: any field the prompt cannot show exactly is refused, so
    // the Owner never approves bytes that say more than the prompt does.
    guard
        let object = try? JSONSerialization.jsonObject(with: payload) as? [String: Any],
        object["schema"] as? String == "nexus.owner_grant_attestation.v1"
    else {
        fail("not a nexus.owner_grant_attestation.v1 payload")
    }
    func text(_ key: String) -> String {
        guard let value = object[key] as? String, !value.isEmpty else { fail("field \(key) must be a non-empty string") }
        return value
    }
    func names(_ key: String, max: Int) -> [String] {
        guard let raw = object[key] as? [Any], !raw.isEmpty, raw.count <= max else {
            fail("field \(key) must list between 1 and \(max) entries")
        }
        let values = raw.compactMap { $0 as? String }
        if values.count != raw.count || Set(values).count != values.count || values.contains(where: \.isEmpty) {
            fail("field \(key) must hold distinct non-empty strings only")
        }
        return values
    }
    guard let issueNumber = object["issue_number"] as? NSNumber,
          CFGetTypeID(issueNumber) == CFNumberGetTypeID(),
          issueNumber.intValue > 0, issueNumber.doubleValue == Double(issueNumber.intValue)
    else {
        fail("field issue_number must be a positive integer")
    }
    let actions = names("allowed_actions", max: 8)
    if actions.contains(where: { $0.range(of: "^[A-Z][A-Z0-9_]{0,63}$", options: .regularExpression) == nil }) {
        fail("allowed_actions must be upper-case names such as GITHUB_MERGE")
    }
    // The gate refuses more than 12 paths; refuse here too so nothing is hidden
    // by a truncated prompt.
    let paths = names("allowed_paths", max: 12)
    return "\(text("owner_id")) grants \(text("agent_login")) \(actions.joined(separator: ", ")) "
        + "on \(text("repository")) issue #\(issueNumber.intValue), paths: \(paths.joined(separator: ", ")), "
        + "valid \(text("issued_at")) to \(text("expires_at"))"
}

func sign(path: String) {
    guard let payload = FileManager.default.contents(atPath: path) else {
        fail("cannot read \(path)")
    }
    let context = LAContext()
    context.localizedReason = summary(of: payload)
    let key = loadKey(context: context)
    do {
        let signature = try key.signature(for: payload)
        print(signature.derRepresentation.base64EncodedString())
    } catch {
        fail("signing was not approved: \(error)")
    }
}

let arguments = CommandLine.arguments
switch arguments.count > 1 ? arguments[1] : "" {
case "init":
    initKey()
case "pubkey":
    printPublicKey(loadKey())
case "sign" where arguments.count == 3:
    sign(path: arguments[2])
default:
    fail("usage: owner-signer init | pubkey | sign PAYLOAD_FILE")
}
