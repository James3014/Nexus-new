#include <unistd.h>

#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.2: PEP 703 Bit-Accurate Alignment
 * 深度對齊 CPython 3.13 Free-threading 內核實作。
 */

// 🧬 PEP 703 狀態位定義 (ob_ref_shared 的最低 2 bits)
#define REF_STATE_MASK   0x03
#define STATE_DEFAULT    0x00
#define STATE_WEAKREFS   0x01
#define STATE_QUEUED     0x02
#define STATE_MERGED     0x03

typedef struct {
    _Atomic uintptr_t ob_tid;        // 擁有者執行緒 ID
    _Atomic uint32_t ob_ref_local;   // 局部引用計數
    _Atomic uintptr_t ob_ref_shared; // 🧬 包含狀態位與共享計數
    uintptr_t data;
} PyObject_PEP703_BitAccurate;

// 🛡️ 輔助函式：提取當前狀態
static inline int get_state(uintptr_t shared) {
    return (int)(shared & REF_STATE_MASK);
}

// 🛡️ v23 代數轉換：CAS 驅動的狀態遷移 (WEAKREFS -> MERGED)
bool try_transition_to_merged(PyObject_PEP703_BitAccurate *obj) {
    uintptr_t expected = atomic_load(&obj->ob_ref_shared);
    while (get_state(expected) == STATE_WEAKREFS) {
        // 設定新狀態位為 MERGED (0b11)，同時保留高位的 refcount
        uintptr_t desired = (expected & ~REF_STATE_MASK) | STATE_MERGED;
        if (atomic_compare_exchange_weak(&obj->ob_ref_shared, &expected, desired)) {
            printf("💀 [CAS] Atomic Transition: WEAKREFS -> MERGED (Success)\n");
            return true;
        }
        // 若失敗，expected 會被 CAS 自動更新為當前值，進入下一輪 loop
    }
    return false;
}

// 🛡️ 模擬 PyWeakref_GetRef 語義
bool mock_PyWeakref_GetRef(PyObject_PEP703_BitAccurate *obj) {
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    
    // 🛡️ Invariant Check: 只有在非 MERGED/QUEUED 狀態下才能獲取弱引用
    if (get_state(shared) == STATE_WEAKREFS) {
        // 🧬 此處應有 Striped Lock 保護 (簡化模擬為原子讀取)
        printf("✅ [Weakref] Valid State (WEAKREFS). Object data: %p\n", (void*)obj->data);
        return true;
    }
    
    printf("🚫 [Weakref] Blocked: Invalid State (%d)\n", get_state(shared));
    return false;
}

void* thread_worker(void* arg) {
    PyObject_PEP703_BitAccurate *obj = (PyObject_PEP703_BitAccurate*)arg;
    
    // 模擬並發：一個執行緒試圖獲取弱引用，另一個試圖切換狀態
    if (!mock_PyWeakref_GetRef(obj)) {
        // 如果獲取失敗，代表物件正在析構或已遷移
    }
    return NULL;
}

int main() {
    PyObject_PEP703_BitAccurate *obj = malloc(sizeof(PyObject_PEP703_BitAccurate));
    atomic_init(&obj->ob_tid, (uintptr_t)pthread_self());
    atomic_init(&obj->ob_ref_local, 1);
    // 初始化狀態為 WEAKREFS (0b01)
    atomic_init(&obj->ob_ref_shared, (uintptr_t)(10 << 2) | STATE_WEAKREFS);
    obj->data = 0xDEADBEEF;

    pthread_t t1;
    printf("🚀 [v23.2 PEP703 Bit-Accurate] Testing CAS State Machine...\n");
    
    pthread_create(&t1, NULL, thread_worker, obj);
    
    // 模擬析構路徑上的狀態遷移
    usleep(1);
    try_transition_to_merged(obj);

    pthread_join(t1, NULL);
    
    // 最終驗證狀態
    uintptr_t final_shared = atomic_load(&obj->ob_ref_shared);
    printf("🏁 [Audit] Final State: %d, Result: %s\n", 
           get_state(final_shared), 
           (get_state(final_shared) == STATE_MERGED) ? "SUCCESS" : "FAILED");

    free(obj);
    return 0;
}
