use std::cell::RefCell;
use std::rc::Rc;

macro_rules! fold_future {
    ($typ:ty) => {
        pub struct FoldedFuture {
            data: Rc<RefCell<Vec<$typ>>>,
        }
        
        impl FoldedFuture {
            pub fn new() -> Self {
                Self {
                    data: Rc::new(RefCell::new(vec![])),
                }
            }
            
            // 這裡有 unsafe 邊界越界風險，模擬 memory leak
            pub unsafe fn leak_edge(&self) {
                let mut data = self.data.borrow_mut();
                data.push(std::mem::transmute(42i32));  // 型別轉換錯誤，導致幽靈引用
            }
        }
    };
}

fold_future!(i32);  // 展開產生 FoldedFuture<i32>
