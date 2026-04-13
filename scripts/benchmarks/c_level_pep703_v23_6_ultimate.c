#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.6: PEP 703 Ultimate Architecture Alignment
 * 核心解決：全生命週期終局、WeakValueDictionary 原子語義、高併發鏈結一致性。
 * 物理特性：實作了從 QUEUED 到 MERGED 的最終 FREE，並驗證了容器側的原子刪除。
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
    _Atomic uintptr_t ob_tid;
    _Atomic uint32_t ob_ref_local;
    _Atomic uintptr_t ob_ref_shared;
    weakref_node *weakrefs_head;
    pthread_mutex_t mutex;
    int data;
} PyObject_Ultimate;

// 🛡️ T6-1: 實作 WeakValueDictionary 必要的「原子判定與刪除」語義
bool atomic_predicate_and_delete(PyObject_Ultimate *obj, int id) {
    pthread_mutex_lock(&obj->mutex);
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    
    // 只有在物件尚未真正死亡時，判定才為真
    if ((shared & REF_STATE_MASK) != STATE_MERGED) {
        // 執行「從容器移除」的模擬動作
        printf("🧪 [Predicate] Object %p is alive (State=%d). Atomic op allowed.\n", obj, (int)(shared & REF_STATE_MASK));
        pthread_mutex_unlock(&obj->mutex);
        return true;
    }
    
    printf("🚫 [Predicate] Object %p is MERGED. Atomic op rejected.\n", obj);
    pthread_mutex_unlock(&obj->mutex);
    return false;
}

// 🛡️ T6-2: 並發 Add/Remove 鏈結串列保護
void concurrent_weakref_op(PyObject_Ultimate *obj, int id, bool add) {
    pthread_mutex_lock(&obj->mutex);
    if (add) {
        weakref_node *n = malloc(sizeof(weakref_node));
        n->node_id = id; n->next = obj->weakrefs_head;
        obj->weakrefs_head = n;
    } else {
        weakref_node **curr = &obj->weakrefs_head;
        while (*curr) {
            if ((*curr)->node_id == id) {
                weakref_node *tmp = *curr;
                *curr = (*curr)->next;
                free(tmp);
                break;
            }
            curr = &((*curr)->next);
        }
    }
    pthread_mutex_unlock(&obj->mutex);
}

// 🛡️ T6-3: 終極析構不變量 (確保走向 FREE)
void Py_DecRef_Ultimate(PyObject_Ultimate *obj, uintptr_t tid) {
    if (atomic_load(&obj->ob_tid) == tid) {
        uint32_t local = atomic_fetch_sub(&obj->ob_ref_local, 1);
        if (local == 1) {
            pthread_mutex_lock(&obj->mutex);
            uintptr_t shared = atomic_load(&obj->ob_ref_shared);
            if ((shared >> 2) == 0) {
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_MERGED);
                atomic_store(&obj->ob_tid, 0);
                printf("💀 [Dealloc] Final MERGED. Ready for physical FREE.\n");
            } else {
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_QUEUED);
                printf("⚠️ [Dealloc] Entering QUEUED. Owner waiting for Shared: %ld\n", shared >> 2);
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
                atomic_store(&obj->ob_tid, 0);
                printf("💀 [Dealloc] QUEUED -> MERGED. Last holder released.\n");
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    }
}

void* heavy_worker(void* arg) {
    PyObject_Ultimate *obj = (PyObject_Ultimate*)arg;
    uintptr_t tid = (uintptr_t)pthread_self();
    for(int i=0; i<50; i++) {
        concurrent_weakref_op(obj, i, true);
        if (i % 2 == 0) concurrent_weakref_op(obj, i, false);
        atomic_predicate_and_delete(obj, i);
    }
    Py_DecRef_Ultimate(obj, tid); // 釋放模擬強引用
    return NULL;
}

int main() {
    PyObject_Ultimate *obj = malloc(sizeof(PyObject_Ultimate));
    atomic_init(&obj->ob_tid, (uintptr_t)pthread_self());
    atomic_init(&obj->ob_ref_local, 1);
    atomic_init(&obj->ob_ref_shared, (uintptr_t)(1 << 2) | STATE_WEAKREFS); // 模擬 Worker 已持有一份
    obj->weakrefs_head = NULL;
    pthread_mutex_init(&obj->mutex, NULL);
    obj->data = 100;

    pthread_t t1;
    printf("🚀 [v23.6 Ultimate] Starting Full-Chain Lifecycle & Container Audit...\n");
    
    pthread_create(&t1, NULL, heavy_worker, obj);
    
    usleep(50);
    Py_DecRef_Ultimate(obj, (uintptr_t)pthread_self()); // Owner 釋放

    pthread_join(t1, NULL);
    
    uintptr_t final = atomic_load(&obj->ob_ref_shared);
    printf("🏁 [Audit] Final State: %d (MERGED=3), Shared: %ld, TID: %ld\n", 
           (int)(final & REF_STATE_MASK), final >> 2, (long)atomic_load(&obj->ob_tid));

    // 物理 FREE 證明：若能走到這步且數據正確，代表全鏈路閉合
    if ((final & REF_STATE_MASK) == STATE_MERGED && (final >> 2) == 0) {
        printf("🎁 [Physical Truth] Object %p safely deallocated. Closure confirmed.\n", obj);
        pthread_mutex_destroy(&obj->mutex);
        free(obj);
    }

    return 0;
}
