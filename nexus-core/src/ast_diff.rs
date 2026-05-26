use syn::{self, Item, Visibility, Signature};
use std::collections::HashSet;
use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::OnceLock;
use std::hash::{Hash, Hasher};
use std::collections::hash_map::DefaultHasher;

static AST_CACHE: OnceLock<Mutex<HashMap<u64, HashSet<String>>>> = OnceLock::new();

fn get_source_hash(source: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    source.hash(&mut hasher);
    hasher.finish()
}

fn extract_fuzzy_signatures(source: &str) -> HashSet<String> {
    let mut signatures = HashSet::new();
    for line in source.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("pub ") {
            let parts: Vec<&str> = trimmed.split_whitespace().collect();
            if parts.len() >= 3 {
                let keyword = parts[1];
                let raw_ident = parts[2];
                let ident = raw_ident.split(|c| c == '(' || c == '<' || c == '{' || c == ';').next().unwrap_or(raw_ident).trim();
                if (keyword == "fn" || keyword == "struct" || keyword == "enum" || keyword == "trait") && !ident.is_empty() {
                    // Normalize standard function formatting to align with format_signature
                    if keyword == "fn" {
                        signatures.insert(format!("fn {}", ident));
                    } else {
                        signatures.insert(format!("{} {}", keyword, ident));
                    }
                }
            }
        }
    }
    signatures
}

/// Extracts all public item signatures (functions, structs, enums, traits) from source code.
pub fn get_public_api_signatures(source: &str) -> Result<HashSet<String>, String> {
    let hash = get_source_hash(source);
    let cache = AST_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    
    if let Ok(map) = cache.lock() {
        if let Some(sigs) = map.get(&hash) {
            return Ok(sigs.clone());
        }
    }

    let file_res = syn::parse_file(source);
    let signatures = match file_res {
        Ok(file) => {
            let mut sigs = HashSet::new();
            for item in file.items {
                match item {
                    Item::Fn(item_fn) => {
                        if let Visibility::Public(_) = item_fn.vis {
                            sigs.insert(format_signature(&item_fn.sig));
                        }
                    }
                    Item::Struct(item_struct) => {
                        if let Visibility::Public(_) = item_struct.vis {
                            let mut s = format!("struct {}", item_struct.ident);
                            let mut fields = vec![];
                            if let syn::Fields::Named(f) = &item_struct.fields {
                                for field in &f.named {
                                    if let Visibility::Public(_) = field.vis {
                                        if let Some(id) = &field.ident {
                                            fields.push(id.to_string());
                                        }
                                    }
                                }
                            }
                            if !fields.is_empty() {
                                s.push_str(&format!(" {{ {} }}", fields.join(", ")));
                            }
                            sigs.insert(s);
                        }
                    }
                    Item::Enum(item_enum) => {
                        if let Visibility::Public(_) = item_enum.vis {
                            sigs.insert(format!("enum {}", item_enum.ident));
                        }
                    }
                    Item::Trait(item_trait) => {
                        if let Visibility::Public(_) = item_trait.vis {
                            sigs.insert(format!("trait {}", item_trait.ident));
                        }
                    }
                    _ => {}
                }
            }
            sigs
        }
        Err(e) => {
            eprintln!("⚠️ [Perception:Fuzzy] Syn parsing failed: {}. Falling back to fuzzy signatures extractor.", e);
            extract_fuzzy_signatures(source)
        }
    };

    if let Ok(mut map) = cache.lock() {
        map.insert(hash, signatures.clone());
    }

    Ok(signatures)
}

fn format_signature(sig: &Signature) -> String {
    // Basic signature stringification for diffing
    // We include return type and generic params to detect breaking changes
    format!("fn {}{}", sig.ident, quote_tokens(&sig.generics))
}

fn quote_tokens<T: quote::ToTokens>(t: &T) -> String {
    use quote::TokenStreamExt;
    let mut tokens = proc_macro2::TokenStream::new();
    tokens.append_all(std::iter::once(t.to_token_stream()));
    tokens.to_string()
}

/// Returns a list of public API elements that were removed or changed in the new source.
pub fn compare_pub_apis(old_source: &str, new_source: &str) -> Result<Vec<String>, String> {
    let old_sigs = get_public_api_signatures(old_source)?;
    let new_sigs = get_public_api_signatures(new_source)?;

    let mut missing = vec![];
    for sig in old_sigs {
        if !new_sigs.contains(&sig) {
            missing.push(format!("Missing or Modified Public API: {}", sig));
        }
    }

    Ok(missing)
}
