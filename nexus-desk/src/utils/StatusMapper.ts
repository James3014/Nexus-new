/**
 * StatusMapper - Nexus 狀態歸一化與中文化中心
 * 負責將異構 API 狀態轉換為直覺的白話中文與決策顏色
 */

export const STATUS_DICTIONARY: Record<string, { label: string; severity: 'neutral' | 'info' | 'success' | 'warning' | 'danger' }> = {
  'INIT': { label: '準備中', severity: 'info' },
  'PLANREADY': { label: '計畫完成', severity: 'info' },
  'DIAGREADY': { label: '診斷完成', severity: 'info' },
  'REPAIRRUNNING': { label: '修補執行中', severity: 'warning' },
  'RSUCCESS': { label: '修補完成', severity: 'info' },
  'APASSED': { label: '稽核通過', severity: 'success' },
  'A_PASSED': { label: '稽核通過', severity: 'success' }, // 正規化處理
  'AUDIT_PASS': { label: '稽核通過', severity: 'success' }, // 正規化處理
  'CRYSTALIZED': { label: '結晶歸檔', severity: 'success' },
  
  // 錯誤終態
  'PLANFAILED': { label: '計畫失敗', severity: 'danger' },
  'DIAGFAILED': { label: '診斷失敗', severity: 'danger' },
  'REPAIRFAILED': { label: '修補失敗', severity: 'danger' },
  'AUDITFAILED': { label: '稽核失敗', severity: 'danger' },
  'SYNCERROR': { label: '同步失敗', severity: 'danger' },
  'TIMEOUTSTALLED': { label: '任務逾時卡住', severity: 'danger' },
  'TAMPERED': { label: '資料遭竄改', severity: 'danger' },
  'VERIFYFATAL': { label: '驗證致命錯誤', severity: 'danger' },
};

export const PHASE_DICTIONARY: Record<string, { name: string; description: string }> = {
  'P': { name: '計畫', description: '整理需求、目標、範圍' },
  'X': { name: '研究', description: '查資料、補上下文、找外部依據' },
  'D': { name: '診斷', description: '找根因，判斷問題真正來源' },
  'R': { name: '修補', description: '修改程式、補測試、執行修復' },
  'A': { name: '稽核', description: '檢查副作用、回歸、證據是否足夠' },
  'C': { name: '結晶', description: '封存成果、整理記憶、完成結案' },
  'UNKNOWN': { name: '未知', description: '查無當前階段資訊' },
};

export const getStatusMeta = (status: string) => {
  const normalized = status.toUpperCase().replace(/_/g, '');
  // 特殊處理：如果有 PASS 則歸類為 APASSED
  if (normalized.includes('PASS') && !normalized.includes('FAIL')) {
      return STATUS_DICTIONARY['APASSED'];
  }
  return STATUS_DICTIONARY[status] || { label: status, severity: 'neutral' };
};
