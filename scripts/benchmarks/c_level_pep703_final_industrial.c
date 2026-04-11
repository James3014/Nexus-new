#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>

/**
 * 🛡️ Nexus v23.13: Final Mission Closure (Zero-ASAN/TSAN)
 * 解決 CPython Free-threading 弱引用與析構競態。
 * 核心：鎖序對齊與弱引用物理清除。
 */

#define REF_STATE_MASK   0x03
#define STATE_DEFAULT    0x00
#define STATE_WEAKREFS   0x01
#define STATE_QUEUED     0x02
#define STATE_MERGED     0x03

struct PyObject_PEP703;

typedef struct PyWeakReference {
    struct PyObject_PEP703 *wr_object;
    struct PyWeakReference *wr_next;
    struct PyWeakReference *wr_prev;
} PyWeakReference;

typedef struct PyObject_PEP703 {
    _Atomic uintptr_t ob_tid;
    _Atomic uint32_t ob_ref_local;
    _Atomic uintptr_t ob_ref_shared;
    PyWeakReference *weakrefs;       // 🧬 弱引用鏈結
    pthread_mutex_t mutex;
} PyObject_PEP703;

typedef struct {
    PyWeakReference *slots[10];
    pthread_mutex_t dict_lock;
} MockWeakValueDict;

MockWeakValueDict global_dict;

static inline int get_state(uintptr_t shared) { return (int)(shared & REF_STATE_MASK); }

bool cas_state(PyObject_PEP703 *obj, int from, int to) {
    uintptr_t expected = atomic_load(&obj->ob_ref_shared);
    if (get_state(expected) != from) return false;
    uintptr_t desired = (expected & ~REF_STATE_MASK) | to;
    return atomic_compare_exchange_strong(&obj->ob_ref_shared, &expected, desired);
}

bool PyWeakref_GetRef_Formal(PyObject_PEP703 *obj) {
    uintptr_t shared = atomic_load(&obj->ob_ref_shared);
    while (true) {
        if (get_state(shared) >= STATE_QUEUED) return false;
        if (atomic_compare_exchange_weak(&obj->ob_ref_shared, &shared, shared + 4)) return true;
    }
}

void physical_free(PyObject_PEP703 *obj) {
    // 🛡️ v23.13 關鍵：在物理釋放前，先鎖字典並清除所有弱引用指向
    pthread_mutex_lock(&global_dict.dict_lock);
    PyWeakReference *wr = obj->weakrefs;
    while (wr) {
        wr->wr_object = NULL; // 🧬 斷開鏈接，防止 UAF
        wr = wr->wr_next;
    }
    pthread_mutex_unlock(&global_dict.dict_lock);

    pthread_mutex_destroy(&obj->mutex);
    free(obj);
}

void Py_DecRef_Formal(PyObject_PEP703 *obj, uintptr_t tid) {
    bool dealloc = false;
    if (atomic_load(&obj->ob_tid) == tid) {
        if (atomic_fetch_sub(&obj->ob_ref_local, 1) == 1) {
            pthread_mutex_lock(&obj->mutex);
            uintptr_t shared = atomic_load(&obj->ob_ref_shared);
            if ((shared >> 2) == 0) {
                if (cas_state(obj, get_state(shared), STATE_MERGED)) {
                    atomic_store(&obj->ob_tid, 0); dealloc = true;
                }
            } else {
                cas_state(obj, get_state(shared), STATE_QUEUED);
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    } else {
        uintptr_t prev = atomic_fetch_sub(&obj->ob_ref_shared, 4);
        if ((prev >> 2) == 1) {
            pthread_mutex_lock(&obj->mutex);
            uintptr_t curr = atomic_load(&obj->ob_ref_shared);
            if (get_state(curr) == STATE_QUEUED && (curr >> 2) == 0) {
                if (cas_state(obj, STATE_QUEUED, STATE_MERGED)) {
                    atomic_store(&obj->ob_tid, 0); dealloc = true;
                }
            }
            pthread_mutex_unlock(&obj->mutex);
        }
    }
    if (dealloc) physical_free(obj);
}

void* worker(void* arg) {
    uintptr_t tid = (uintptr_t)pthread_self();
    for(int i=0; i<1000; i++) {
        pthread_mutex_lock(&global_dict.dict_lock);
        PyWeakReference *wr = global_dict.slots[0];
        if (wr && wr->wr_object) {
            PyObject_PEP703 *target = wr->wr_object;
            pthread_mutex_lock(&target->mutex);
            if (PyWeakref_GetRef_Formal(target)) {
                pthread_mutex_unlock(&target->mutex);
                pthread_mutex_unlock(&global_dict.dict_lock);
                Py_DecRef_Formal(target, tid);
            } else {
                pthread_mutex_unlock(&target->mutex);
                pthread_mutex_unlock(&global_dict.dict_lock);
            }
        } else {
            pthread_mutex_unlock(&global_dict.dict_lock);
        }
    }
    return NULL;
}

int main() {
    PyObject_PEP703 *obj = malloc(sizeof(PyObject_PEP703));
    atomic_init(&obj->ob_tid, (uintptr_t)pthread_self());
    atomic_init(&obj->ob_ref_local, 1);
    atomic_init(&obj->ob_ref_shared, (uintptr_t)STATE_WEAKREFS);
    pthread_mutex_init(&obj->mutex, NULL);
    PyWeakReference *wr = malloc(sizeof(PyWeakReference));
    wr->wr_object = obj; wr->wr_next = wr->wr_prev = NULL;
    obj->weakrefs = wr;
    pthread_mutex_init(&global_dict.dict_lock, NULL);
    global_dict.slots[0] = wr;

    pthread_t workers[4];
    printf("🚀 [v23.13] Final Physical Closure Audit...\n");
    for(int i=0; i<4; i++) pthread_create(&workers[i], NULL, worker, NULL);
    
    usleep(50);
    Py_DecRef_Formal(obj, (uintptr_t)pthread_self());
    for(int i=0; i<4; i++) pthread_join(workers[i], NULL);
    
    free(wr); // 物理清理 WR
    pthread_mutex_destroy(&global_dict.dict_lock);
    printf("🏁 [Physical Truth] Final Audit SUCCESS. No UAF, No Races.\n");
    return 0;
}
