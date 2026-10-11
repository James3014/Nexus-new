// owner-signer: sign Nexus Owner grants with a Touch ID–gated Secure Enclave key (#1750 phase 2).
//
// The private key is created inside the Secure Enclave and never leaves it; the
// file on disk is an opaque handle that only this Mac's Secure Enclave can use.
// Every signature requires a fresh biometric check, so a process running under
// the Owner's account cannot sign without the Owner's finger.
//
//   owner-signer init            create the key (once) and print the public key
//   owner-signer pubkey          print the public key PEM
//   owner-signer sign FILE       Touch ID prompt, then print the base64 DER signature
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
        [.privateKeyUsage, .biometryCurrentSet],
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
    guard
        let object = try? JSONSerialization.jsonObject(with: payload) as? [String: Any],
        object["schema"] as? String == "nexus.owner_grant_attestation.v1"
    else {
        fail("not a nexus.owner_grant_attestation.v1 payload")
    }
    let repository = object["repository"] as? String ?? "?"
    let owner = object["owner_id"] as? String ?? "?"
    let agent = object["agent_login"] as? String ?? "?"
    let issue = (object["issue_number"] as? NSNumber)?.stringValue ?? "?"
    let actions = (object["allowed_actions"] as? [String] ?? []).joined(separator: ", ")
    let pathList = object["allowed_paths"] as? [String] ?? []
    // The gate refuses more than 12 paths; refuse here too so nothing is hidden
    // by a truncated prompt.
    if pathList.isEmpty || pathList.count > 12 { fail("grant must name between 1 and 12 paths") }
    let paths = pathList.joined(separator: ", ")
    let issued = object["issued_at"] as? String ?? "?"
    let expires = object["expires_at"] as? String ?? "?"
    return "\(owner) grants \(agent) \(actions) on \(repository) issue #\(issue), paths: \(paths), valid \(issued) to \(expires)"
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
