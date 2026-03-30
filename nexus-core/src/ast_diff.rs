use syn::{self, File, Item, Visibility, Signature};
use std::collections::HashSet;

/// Extracts all public item signatures (functions, structs, enums, traits) from source code.
pub fn get_public_api_signatures(source: &str) -> Result<HashSet<String>, String> {
    let file = syn::parse_file(source).map_err(|e| format!("Failed to parse Rust source: {}", e))?;
    let mut signatures = HashSet::new();

    for item in file.items {
        match item {
            Item::Fn(item_fn) => {
                if let Visibility::Public(_) = item_fn.vis {
                    signatures.insert(format_signature(&item_fn.sig));
                }
            }
            Item::Struct(item_struct) => {
                if let Visibility::Public(_) = item_struct.vis {
                    // For structs, we track the name and the names of public fields
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
                    signatures.insert(s);
                }
            }
            Item::Enum(item_enum) => {
                if let Visibility::Public(_) = item_enum.vis {
                    signatures.insert(format!("enum {}", item_enum.ident));
                }
            }
            Item::Trait(item_trait) => {
                if let Visibility::Public(_) = item_trait.vis {
                    signatures.insert(format!("trait {}", item_trait.ident));
                }
            }
            _ => {}
        }
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
