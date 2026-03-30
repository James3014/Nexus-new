// Acheron Paradox Core: Folding Future Macro
macro_rules! fold_future {
    ($t:ty) => {
        struct SpectralWrapper<'a> {
            inner: &'a $t,
            phantom: std::marker::PhantomData<*const ()>,
        }
    };
}

fold_future!(u32);
