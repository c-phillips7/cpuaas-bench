// Model 1 workload: stateless. Same stdio protocol as workloads/model1.py.
use std::io::{self, BufRead, Write};

fn compute(n: u64) -> u64 { (0..n).map(|i| i * i).sum() }

fn main() {
    println!("READY");
    io::stdout().flush().unwrap();
    for line in io::stdin().lock().lines() {
        let n: u64 = line.unwrap().trim().parse().unwrap();
        println!("{}", compute(n));
        io::stdout().flush().unwrap();
    }
}
