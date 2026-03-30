use proc_macro::TokenStream;

#[proc_macro]
pub fn bridge_macro(_input: TokenStream) -> TokenStream {
    // 簡化：直接展開 FoldedFuture 依賴
    "type BridgeType = super::quantum::FoldedFuture;".parse().unwrap()
}
