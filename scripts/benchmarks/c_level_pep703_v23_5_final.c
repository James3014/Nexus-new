#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.5: PEP 703 Final State-Progression Alignment
 * 核心解決：CAS 狀態轉換、ob_tid 清理、以及弱引用全生命週期管理。
 */

#define REF_STATE_MASK   0x03
#define STATE_DEFAULT    0x00
#define STATE_WEAKREFS   0x01
#define STATE_QUEUED     0x02
#define STATE_MERGED     0x03

typedef struct weakref_node {
    struct weakref_node *next;
    int node_id;
} weakref_node;

typedef struct {
    _Atomic uintptr_t ob_tid;        // 🧬 可被原子清理的 Thread ID
    _Atomic uint32_t ob_ref_local;
    _Atomic uintptr_t ob_ref_shared;
    weakref_node *weakrefs_head;
    pthread_mutex_t mutex;
} PyObject_Final;

// 🛡️ T3-1: 實作基於 CAS 的狀態單調遞增
bool transition_state(PyObject_Final *obj, int from, int to) {
    uintptr_t expected = atomic_load(&obj->ob_ref_shared);
    if ((expected & REF_STATE_MASK) != from) return false;
    uintptr_t desired = (expected & ~REF_STATE_MASK) | to;
    return atomic_compare_exchange_weak(&obj->ob_ref_shared, &expected, desired);
}

// 🛡️ T3-2: 實作並發移除弱引用 (remove_weakref)
void remove_weakref(PyObject_Final *obj, int id) {
    pthread_mutex_lock(&obj->mutex);
    weakref_node **curr = &obj->weakrefs_head;
    while (*curr) {
        if ((*curr)->node_id == id) {
            weakref_node *to_free = *curr;
            *curr = (*curr)->next;
            free(to_free);
            printf("🗑️ [Weakref] Removed Node ID: %d\n", id);
            break;
        }
        curr = &((*curr)->next);
    }
    pthread_mutex_unlock(&obj->mutex);
}

// 🛡️ T3-3: 硬化 PyWeakref_GetRef (取得強引用保證)
bool PyWeakref_GetRef_Hardened(PyObject_Final *obj) {
    pthread_mutex_lock(&obj->mutex);
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    int state = (int)(shared & REF_STATE_MASK);
    
    if (state == STATE_DEFAULT || state == STATE_WEAKREFS) {
        atomic_fetch_add(&obj->ob_ref_shared, 4); // 增量強引用
        pthread_mutex_unlock(&obj->mutex);
        return true;
    }
    pthread_mutex_unlock(&obj->mutex);
    return false;
}

// 🛡️ T3-4: 終極硬化析構 (含 ob_tid 清理)
void Py_DecRef_Final(PyObject_Final *obj, uintptr_t tid) {
    uintptr_t owner = atomic_load(&obj->ob_tid);
    if (owner == tid) {
        uint32_t local = atomic_fetch_sub(&obj->ob_ref_local, 1);
        if (local == 1) {
            pthread_mutex_lock(&obj->mutex);
            uintptr_t shared = atomic_load(&obj->ob_ref_shared);
            if ((shared >> 2) == 0) {
                // 進入 MERGED 並清理 ob_tid
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_MERGED);
                atomic_store(&obj->ob_tid, 0); // 🧬 PEP 703 對齊：清理擁有者
                printf("💀 [DecRef] Final MERGED & TID Cleaned (Local=0, Shared=0)\n");
            } else {
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_QUEUED);
                printf("⚠️ [DecRef] Entering QUEUED (Shared still > 0)\n");
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    } else {
        uintptr_t prev = atomic_fetch_sub(&obj->ob_ref_shared, 4);
        if ((prev >> 2) == 1) {
            pthread_mutex_lock(&obj->mutex);
            uintptr_t curr = atomic_load(&obj->ob_ref_shared);
            if ((curr & REF_STATE_MASK) == STATE_QUEUED) {
                atomic_store(&obj->ob_ref_shared, (curr & ~REF_STATE_MASK) | STATE_MERGED);
                atomic_store(&obj->ob_tid, 0); // 🧬 由最後一個 Non-owner 清理
                printf("💀 [DecRef] QUEUED -> MERGED Completed by Non-owner\n");
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    }
}

void* worker_thread(void* arg) {
    PyObject_Final *obj = (PyObject_Final*)arg;
    uintptr_t tid = (uintptr_t)pthread_self();
    
    // 1. 取得引用
    if (PyWeakref_GetRef_Hardened(obj)) {
        printf("✅ [Worker] Reference upgraded. Safe to use.\n");
        usleep(200); // 持有時間超過 Owner 析構嘗試
        // 2. 使用完畢釋放
        Py_DecRef_Final(obj, tid);
    }
    return NULL;
}

int main() {
    PyObject_Final *obj = malloc(sizeof(PyObject_Final));
    atomic_init(&obj->ob_tid, (uintptr_t)pthread_self());
    atomic_init(&obj->ob_ref_local, 1);
    atomic_init(&obj->ob_ref_shared, (uintptr_t)(1 << 2) | STATE_WEAKREFS);
    obj->weakrefs_head = NULL;
    pthread_mutex_init(&obj->mutex, NULL);

    pthread_t t1;
    printf("🚀 [v23.5 Final] Launching Bit-Accurate Closure Test...\n");
    
    pthread_create(&t1, NULL, worker_thread, obj);
    
    usleep(100);
    Py_DecRef_Final(obj, (uintptr_t)pthread_self());

    pthread_join(t1, NULL);
    
    uintptr_t final = atomic_load(&obj->ob_ref_shared);
    printf("🏁 [Final Audit] State: %d, TID: %ld, Shared: %ld\n", 
           (int)(final & REF_STATE_MASK), (long)atomic_load(&obj->ob_tid), final >> 2);

    pthread_mutex_destroy(&obj->mutex);
    free(obj);
    return 0;
}
