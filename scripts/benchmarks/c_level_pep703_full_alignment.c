#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.3: PEP 703 Full Architecture Alignment
 * 深度對齊 CPython 3.13 內核：Biased Refcounting, QUEUED State, and Ref-Upgrade.
 */

#define REF_STATE_MASK   0x03
#define STATE_DEFAULT    0x00
#define STATE_WEAKREFS   0x01
#define STATE_QUEUED     0x02
#define STATE_MERGED     0x03

typedef struct weakref_node {
    struct weakref_node *next;
    _Atomic int is_active;
} weakref_node;

typedef struct {
    uintptr_t ob_tid;                // Owner Thread ID
    _Atomic uint32_t ob_ref_local;   // Local count (Owner only)
    _Atomic uintptr_t ob_ref_shared; // [RefCount (62) | State (2)]
    _Atomic weakref_node *weakrefs;  // Linked list of weakrefs
    pthread_mutex_t mutex;           // Per-object lock for critical sections
} PyObject_Full;

// 🛡️ 核心：安全引用升級 (PyWeakref_GetRef Equivalent)
bool PyWeakref_GetRef_v23(PyObject_Full *obj) {
    pthread_mutex_lock(&obj->mutex);
    
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    int state = (int)(shared & REF_STATE_MASK);
    
    // Invariant: 只有在 DEFAULT 或 WEAKREFS 狀態下才能獲取強引用
    if (state == STATE_DEFAULT || state == STATE_WEAKREFS) {
        // 原子增量共享引用計數 (加 4 因為最低 2 bits 是狀態)
        atomic_fetch_add(&obj->ob_ref_shared, 4);
        printf("✅ [GetRef] Success: State=%d, Refcount Incremented\n", state);
        pthread_mutex_unlock(&obj->mutex);
        return true;
    }
    
    printf("🚫 [GetRef] Refused: Object in transition state %d\n", state);
    pthread_mutex_unlock(&obj->mutex);
    return false;
}

// 🛡️ 模擬 Biased Refcount 釋放邏輯
void Py_DecRef_v23(PyObject_Full *obj, uintptr_t current_tid) {
    if (obj->ob_tid == current_tid) {
        // Owner: 操作 local count
        uint32_t count = atomic_fetch_sub(&obj->ob_ref_local, 1);
        if (count == 1) {
            printf("💀 [DecRef] Owner triggered dealloc path\n");
            // 進入析構：遷移至 MERGED
            pthread_mutex_lock(&obj->mutex);
            uintptr_t shared = atomic_load(&obj->ob_ref_shared);
            atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_MERGED);
            pthread_mutex_unlock(&obj->mutex);
        }
    } else {
        // Non-owner: 操作 shared count 並可能觸發 QUEUED
        uintptr_t shared = atomic_fetch_sub(&obj->ob_ref_shared, 4);
        if ((shared >> 2) == 1) {
            printf("⚠️ [DecRef] Non-owner triggered QUEUED state\n");
            pthread_mutex_lock(&obj->mutex);
            atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_QUEUED);
            pthread_mutex_unlock(&obj->mutex);
        }
    }
}

void* non_owner_thread(void* arg) {
    PyObject_Full *obj = (PyObject_Full*)arg;
    uintptr_t tid = (uintptr_t)pthread_self();
    
    usleep(100);
    // 1. 嘗試獲取弱引用並升級
    if (PyWeakref_GetRef_v23(obj)) {
        // 模擬使用
        usleep(10);
        // 2. 釋放引用
        Py_DecRef_v23(obj, tid);
    }
    return NULL;
}

int main() {
    PyObject_Full *obj = malloc(sizeof(PyObject_Full));
    obj->ob_tid = (uintptr_t)pthread_self();
    atomic_init(&obj->ob_ref_local, 1);
    atomic_init(&obj->ob_ref_shared, (uintptr_t)(5 << 2) | STATE_WEAKREFS);
    obj->weakrefs = NULL;
    pthread_mutex_init(&obj->mutex, NULL);

    pthread_t t1;
    printf("🚀 [v23.3 PEP703 Full Alignment] Testing Full State Machine & Biased Refcounting...\n");
    
    pthread_create(&t1, NULL, non_owner_thread, obj);
    
    // 主執行緒 (Owner) 執行任務
    usleep(50);
    Py_DecRef_v23(obj, obj->ob_tid);

    pthread_join(t1, NULL);
    
    uintptr_t final_shared = atomic_load(&obj->ob_ref_shared);
    printf("🏁 [Audit] Final State Bits: %d, Shared Refcount: %ld\n", 
           (int)(final_shared & REF_STATE_MASK), final_shared >> 2);

    pthread_mutex_destroy(&obj->mutex);
    free(obj);
    return 0;
}
