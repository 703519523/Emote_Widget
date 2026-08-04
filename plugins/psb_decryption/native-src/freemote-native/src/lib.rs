use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyModule};

const NATIVE_API_VERSION: u32 = 1;
const FRAME_SIZE: usize = 0x1000;

#[derive(Debug, PartialEq, Eq)]
enum UnpackError { Truncated { input_offset: usize }, OutputSizeMismatch }

fn declared_size(input: &[u8]) -> PyResult<usize> {
    let bytes: [u8; 4] = input.get(..4).ok_or_else(|| PyValueError::new_err("truncated PSP shell"))?
        .try_into().expect("slice length checked");
    let size = u32::from_le_bytes(bytes) as usize;
    if size < 4 || size > isize::MAX as usize {
        return Err(PyValueError::new_err(format!("invalid PSP decompressed size: {size}")));
    }
    Ok(size)
}

fn unpack_psp_impl(input: &[u8], output: &mut [u8]) -> Result<(), UnpackError> {
    if output.len() != u32::from_le_bytes(input[..4].try_into().unwrap()) as usize {
        return Err(UnpackError::OutputSizeMismatch);
    }
    let mut frame = [0_u8; FRAME_SIZE];
    let (mut frame_pos, mut src, mut dst) = (1_usize, 4_usize, 0_usize);
    while dst < output.len() {
        let control = *input.get(src).ok_or(UnpackError::Truncated { input_offset: src })?;
        src += 1;
        for bit in 0..8 {
            if dst == output.len() { break; }
            if control & (1 << bit) != 0 {
                let value = *input.get(src).ok_or(UnpackError::Truncated { input_offset: src })?;
                src += 1;
                frame[frame_pos & 0xFFF] = value; frame_pos += 1;
                output[dst] = value; dst += 1;
            } else {
                let pair = input.get(src..src + 2).ok_or(UnpackError::Truncated { input_offset: src })?;
                src += 2;
                let mut offset = ((pair[0] as usize) << 4) | ((pair[1] as usize) >> 4);
                for _ in 0..2 + (pair[1] as usize & 0xF) {
                    if dst == output.len() { break; }
                    let value = frame[offset & 0xFFF]; offset += 1;
                    frame[frame_pos & 0xFFF] = value; frame_pos += 1;
                    output[dst] = value; dst += 1;
                }
            }
        }
    }
    Ok(())
}

#[pyfunction]
fn api_version() -> u32 { NATIVE_API_VERSION }

#[pyfunction]
fn capabilities() -> Vec<&'static str> { vec!["psp_lzss_unpack"] }

#[pyfunction]
fn unpack_psp<'py>(py: Python<'py>, input: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let size = declared_size(input)?;
    PyBytes::new_with(py, size, |output| unpack_psp_impl(input, output).map_err(|error| match error {
        UnpackError::Truncated { input_offset } => PyValueError::new_err(
            format!("truncated PSP LZSS stream at input offset {input_offset}")),
        UnpackError::OutputSizeMismatch => PyValueError::new_err("native PSP output size mismatch"),
    }))
}

#[pymodule]
fn _freemote_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(api_version, module)?)?;
    module.add_function(wrap_pyfunction!(capabilities, module)?)?;
    module.add_function(wrap_pyfunction!(unpack_psp, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn literals_and_overlapping_back_reference() {
        let input = [8, 0, 0, 0, 0x07, b'A', b'B', b'C', 0x00, 0x13];
        let mut output = [0_u8; 8];
        unpack_psp_impl(&input, &mut output).unwrap();
        assert_eq!(&output, b"ABCABCAB");
    }
    #[test]
    fn reports_truncated_offsets() {
        let mut output = [0_u8; 4];
        assert_eq!(unpack_psp_impl(&[4, 0, 0, 0], &mut output), Err(UnpackError::Truncated { input_offset: 4 }));
        assert_eq!(unpack_psp_impl(&[4, 0, 0, 0, 1], &mut output), Err(UnpackError::Truncated { input_offset: 5 }));
        assert_eq!(unpack_psp_impl(&[4, 0, 0, 0, 0, 1], &mut output), Err(UnpackError::Truncated { input_offset: 5 }));
    }
}