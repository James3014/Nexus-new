use std::io::{self, BufRead, BufReader, Read, Seek, SeekFrom};
use std::fs::File;
use std::path::Path;
use serde::{Serialize, Deserialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct LogEvent {
    pub kind: String,
    pub task_id: String,
    pub line: String,
    pub ansi: bool,
    pub ts: String,
}

pub struct LogStream {
    file: File,
    pos: u64,
}

impl LogStream {
    pub fn new<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let file = File::open(path)?;
        let pos = file.metadata()?.len();
        Ok(Self { file, pos })
    }
    
    pub fn tail(&mut self) -> io::Result<Vec<String>> {
        self.file.seek(SeekFrom::Start(self.pos))?;
        let reader = BufReader::new(self.file.by_ref());
        let mut lines = Vec::new();
        for line in reader.lines() {
            if let Ok(l) = line {
                lines.push(l);
            }
        }
        self.pos = self.file.metadata()?.len();
        Ok(lines)
    }
}
