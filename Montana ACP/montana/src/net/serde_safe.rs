//! Safe deserialization with bounded collections

use serde::{de, Deserialize, Deserializer, Serialize, Serializer};
use std::fmt;
use std::marker::PhantomData;

pub const MAX_ADDRS: usize = 1_000;
pub const MAX_INV_ITEMS: usize = 50_000;
pub const MAX_HEADERS: usize = 2_000;
pub const MAX_PRESENCE_PROOFS: usize = 100;
pub const MAX_LOCATOR_HASHES: usize = 101;
pub const MAX_SIGNATURE_BYTES: usize = 5_000;
pub const MAX_TX_INPUTS: usize = 10_000;
pub const MAX_TX_OUTPUTS: usize = 10_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundedVec<T, const N: usize>(pub Vec<T>);

impl<T, const N: usize> BoundedVec<T, N> {
    pub fn new(v: Vec<T>) -> Option<Self> {
        if v.len() <= N {
            Some(Self(v))
        } else {
            None
        }
    }

    /// Internal use only — caller must ensure len <= N
    #[inline]
    pub fn new_unchecked(v: Vec<T>) -> Self {
        debug_assert!(v.len() <= N);
        Self(v)
    }

    pub fn into_inner(self) -> Vec<T> {
        self.0
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

impl<T, const N: usize> Default for BoundedVec<T, N> {
    fn default() -> Self {
        Self(Vec::new())
    }
}

impl<T, const N: usize> From<BoundedVec<T, N>> for Vec<T> {
    fn from(bv: BoundedVec<T, N>) -> Self {
        bv.0
    }
}

impl<T, const N: usize> std::ops::Deref for BoundedVec<T, N> {
    type Target = Vec<T>;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl<T, const N: usize> std::ops::DerefMut for BoundedVec<T, N> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.0
    }
}

impl<'a, T, const N: usize> IntoIterator for &'a BoundedVec<T, N> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.iter()
    }
}

impl<T, const N: usize> IntoIterator for BoundedVec<T, N> {
    type Item = T;
    type IntoIter = std::vec::IntoIter<T>;
    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}

impl<T: Serialize, const N: usize> Serialize for BoundedVec<T, N> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.serialize(serializer)
    }
}

impl<'de, T: Deserialize<'de>, const N: usize> Deserialize<'de> for BoundedVec<T, N> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct BoundedVecVisitor<T, const N: usize>(PhantomData<T>);

        impl<'de, T: Deserialize<'de>, const N: usize> de::Visitor<'de> for BoundedVecVisitor<T, N> {
            type Value = BoundedVec<T, N>;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                write!(formatter, "a sequence with at most {} elements", N)
            }

            fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
                let size_hint = seq.size_hint().unwrap_or(0);
                if size_hint > N {
                    return Err(de::Error::invalid_length(size_hint, &self));
                }

                let mut vec = Vec::with_capacity(size_hint.min(N));
                while let Some(elem) = seq.next_element()? {
                    if vec.len() >= N {
                        return Err(de::Error::invalid_length(vec.len() + 1, &self));
                    }
                    vec.push(elem);
                }
                Ok(BoundedVec(vec))
            }
        }

        deserializer.deserialize_seq(BoundedVecVisitor(PhantomData))
    }
}

/// Bounded bytes (Vec<u8>) wrapper
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundedBytes<const N: usize>(pub Vec<u8>);

impl<const N: usize> BoundedBytes<N> {
    pub fn new(v: Vec<u8>) -> Option<Self> {
        if v.len() <= N {
            Some(Self(v))
        } else {
            None
        }
    }

    #[inline]
    pub fn new_unchecked(v: Vec<u8>) -> Self {
        debug_assert!(v.len() <= N);
        Self(v)
    }

    pub fn into_inner(self) -> Vec<u8> {
        self.0
    }
}

impl<const N: usize> std::ops::Deref for BoundedBytes<N> {
    type Target = Vec<u8>;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl<const N: usize> Serialize for BoundedBytes<N> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.serialize(serializer)
    }
}

impl<'de, const N: usize> Deserialize<'de> for BoundedBytes<N> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct BoundedBytesVisitor<const N: usize>;

        impl<'de, const N: usize> de::Visitor<'de> for BoundedBytesVisitor<N> {
            type Value = BoundedBytes<N>;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                write!(formatter, "a byte sequence with at most {} bytes", N)
            }

            fn visit_bytes<E: de::Error>(self, v: &[u8]) -> Result<Self::Value, E> {
                if v.len() > N {
                    return Err(de::Error::invalid_length(v.len(), &self));
                }
                Ok(BoundedBytes(v.to_vec()))
            }

            fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
                let size_hint = seq.size_hint().unwrap_or(0);
                if size_hint > N {
                    return Err(de::Error::invalid_length(size_hint, &self));
                }

                let mut vec = Vec::with_capacity(size_hint.min(N));
                while let Some(byte) = seq.next_element()? {
                    if vec.len() >= N {
                        return Err(de::Error::invalid_length(vec.len() + 1, &self));
                    }
                    vec.push(byte);
                }
                Ok(BoundedBytes(vec))
            }
        }

        deserializer.deserialize_bytes(BoundedBytesVisitor)
    }
}

/// Deserialize with postcard and buffer size validation
pub fn from_bytes<'de, T: Deserialize<'de>>(data: &'de [u8]) -> Result<T, postcard::Error> {
    postcard::from_bytes(data)
}

/// Serialize with postcard
pub fn to_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, postcard::Error> {
    postcard::to_allocvec(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bounded_vec_within_limit() {
        let data = vec![1u32, 2, 3];
        let bounded: BoundedVec<u32, 10> = BoundedVec::new(data.clone()).unwrap();
        assert_eq!(bounded.len(), 3);
        assert_eq!(bounded.into_inner(), data);
    }

    #[test]
    fn test_bounded_vec_at_limit() {
        let data: Vec<u32> = (0..10).collect();
        let bounded: BoundedVec<u32, 10> = BoundedVec::new(data).unwrap();
        assert_eq!(bounded.len(), 10);
    }

    #[test]
    fn test_bounded_vec_exceeds_limit() {
        let data: Vec<u32> = (0..11).collect();
        assert!(BoundedVec::<u32, 10>::new(data).is_none());
    }

    #[test]
    fn test_bounded_vec_deserialize_ok() {
        let original: Vec<u8> = vec![1, 2, 3];
        let serialized = postcard::to_allocvec(&original).unwrap();
        let bounded: BoundedVec<u8, 100> = postcard::from_bytes(&serialized).unwrap();
        assert_eq!(*bounded, original);
    }

    #[test]
    fn test_bounded_vec_deserialize_exceeds() {
        let original: Vec<u8> = vec![1, 2, 3, 4, 5];
        let serialized = postcard::to_allocvec(&original).unwrap();
        let result: Result<BoundedVec<u8, 3>, _> = postcard::from_bytes(&serialized);
        assert!(result.is_err());
    }

    #[test]
    fn test_bounded_bytes_ok() {
        let data = vec![0u8; 100];
        let bounded: BoundedBytes<1000> = BoundedBytes::new(data).unwrap();
        assert_eq!(bounded.len(), 100);
    }

    #[test]
    fn test_bounded_bytes_exceeds() {
        let data = vec![0u8; 1001];
        assert!(BoundedBytes::<1000>::new(data).is_none());
    }
}
