#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.4: PEP 703 Hardened Lifecycle Alignment
 * 解決 v23.3 中的析構不變量破洞：確保全鏈路引用清零與鏈結完整性。
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
    uintptr_t ob_tid;
    _Atomic uint32_t ob_ref_local;
    _Atomic uintptr_t ob_ref_shared;
    weakref_node *weakrefs_head; // 🧬 實體鏈結串列
    pthread_mutex_t mutex;
} PyObject_Hardened;

// 🛡️ 輔助：安全添加弱引用節點
void add_weakref(PyObject_Hardened *obj, int id) {
    pthread_mutex_lock(&obj->mutex);
    if ((atomic_load(&obj->ob_ref_shared) & REF_STATE_MASK) <= STATE_WEAKREFS) {
        weakref_node *new_node = malloc(sizeof(weakref_node));
        new_node->node_id = id;
        new_node->next = obj->weakrefs_head;
        obj->weakrefs_head = new_node;
        // 確保狀態切換到 WEAKREFS
        uintptr_t current = atomic_load(&obj->ob_ref_shared);
        atomic_store(&obj->ob_ref_shared, current | STATE_WEAKREFS);
    }
    pthread_mutex_unlock(&obj->mutex);
}

// 🛡️ 核心：解決 v23.3 矛盾的硬化 DecRef
void Py_DecRef_Hardened(PyObject_Hardened *obj, uintptr_t current_tid) {
    if (obj->ob_tid == current_tid) {
        uint32_t local = atomic_fetch_sub(&obj->ob_ref_local, 1);
        if (local == 1) {
            // Owner 嘗試析構，但必須檢查共享引用
            pthread_mutex_lock(&obj->mutex);
            uintptr_t shared = atomic_load(&obj->ob_ref_shared);
            if ((shared >> 2) == 0) {
                // 🛡️ Invariant Met: 雙計數器均為 0，安全進入 MERGED
                printf("💀 [DecRef] Final Dealloc: Local and Shared are both 0.\n");
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_MERGED);
                
                // 物理清理 Linked List
                weakref_node *curr = obj->weakrefs_head;
                while(curr) {
                    weakref_node *next = curr->next;
                    free(curr);
                    curr = next;
                }
                obj->weakrefs_head = NULL;
            } else {
                // 🛡️ Invariant Guard: 仍有共享引用，進入 QUEUED 等待合併
                printf("⚠️ [DecRef] Local is 0 but Shared is %ld. Entering QUEUED.\n", shared >> 2);
                atomic_store(&obj->ob_ref_shared, (shared & ~REF_STATE_MASK) | STATE_QUEUED);
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    } else {
        // Non-owner 釋放
        uintptr_t prev_shared = atomic_fetch_sub(&obj->ob_ref_shared, 4);
        if ((prev_shared >> 2) == 1) {
            // 共享計數歸零，若已在 QUEUED 狀態，則由最後一個 Non-owner 觸發 MERGED
            pthread_mutex_lock(&obj->mutex);
            uintptr_t current = atomic_load(&obj->ob_ref_shared);
            if ((current & REF_STATE_MASK) == STATE_QUEUED) {
                printf("💀 [DecRef] Last Non-owner transitioning QUEUED -> MERGED\n");
                atomic_store(&obj->ob_ref_shared, (current & ~REF_STATE_MASK) | STATE_MERGED);
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    }
}

// 🛡️ 安全引用升級
bool PyWeakref_GetRef_Hardened(PyObject_Hardened *obj) {
    pthread_mutex_lock(&obj->mutex);
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    int state = (int)(shared & REF_STATE_MASK);
    
    if (state == STATE_DEFAULT || state == STATE_WEAKREFS) {
        atomic_fetch_add(&obj->ob_ref_shared, 4);
        pthread_mutex_unlock(&obj->mutex);
        return true;
    }
    pthread_mutex_unlock(&obj->mutex);
    return false;
}

void* stress_thread(void* arg) {
    PyObject_Hardened *obj = (PyObject_Hardened*)arg;
    uintptr_t tid = (uintptr_t)pthread_self();
    for(int i=0; i<100; i++) {
        add_weakref(obj, i);
        if (PyWeakref_GetRef_Hardened(obj)) {
            Py_DecRef_Hardened(obj, tid);
        }
    }
    return NULL;
}

int main() {
    PyObject_Hardened *obj = malloc(sizeof(PyObject_Hardened));
    obj->ob_tid = (uintptr_t)pthread_self();
    atomic_init(&obj->ob_ref_local, 1);
    atomic_init(&obj->ob_ref_shared, (uintptr_t)STATE_DEFAULT);
    obj->weakrefs_head = NULL;
    pthread_mutex_init(&obj->mutex, NULL);

    pthread_t t1, t2;
    printf("🚀 [v23.4 Hardened] Launching High-Pressure Lifecycle Audit...\n");
    
    pthread_create(&t1, NULL, stress_thread, obj);
    pthread_create(&t2, NULL, stress_thread, obj);
    
    usleep(500);
    Py_DecRef_Hardened(obj, obj->ob_tid);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    
    uintptr_t final = atomic_load(&obj->ob_ref_shared);
    printf("🏁 [Final Audit] State: %d, Shared Count: %ld, Local: %d\n", 
           (int)(final & REF_STATE_MASK), final >> 2, atomic_load(&obj->ob_ref_local));

    pthread_mutex_destroy(&obj->mutex);
    free(obj);
    return 0;
}
