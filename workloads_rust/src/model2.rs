// Model 2 workload: stateful across invocations. Mirrors workloads/model2.py.
use std::io::{self, BufRead, Write};

fn compute(n: u64) -> u64 { (0..n).map(|i| i * i).sum() }

fn main() {
    println!("READY");
    io::stdout().flush().unwrap();
    let mut total: u64 = 0;
    for line in io::stdin().lock().lines() {
        let n: u64 = line.unwrap().trim().parse().unwrap();
        total += compute(n);
        println!("{}", total);
        io::stdout().flush().unwrap();
    }
}
