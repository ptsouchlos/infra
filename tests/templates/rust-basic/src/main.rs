fn twice(value: i32) -> i32 {
    value * 2
}

fn main() {
    println!("{}", twice(2));
}

#[cfg(test)]
mod tests {
    use super::twice;

    #[test]
    fn doubles() {
        assert_eq!(twice(2), 4);
    }
}
